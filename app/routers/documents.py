import logging
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Form, BackgroundTasks
from sqlalchemy.orm import Session
from uuid import uuid4
import aiofiles
import os
from datetime import datetime
from app.database import get_db
from app.services.auth import get_current_user
from app.models.document import Document, DocumentChunk
from app.schemas.document import (
    DocumentUploadResponse,
    DocumentResponse,
    ChunkResponse,
)
from app.ingestion.pdf import pdf_extractor
from app.ingestion.docx_extractor import docx_extractor
from app.rag.retriever import rag_retriever

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/documents", tags=["Documents"])

ALLOWED_EXTENSIONS = {"pdf", "docx", "xlsx", "txt"}
UPLOAD_DIR = "uploads/documents"

os.makedirs(UPLOAD_DIR, exist_ok=True)


def get_file_extension(filename: str) -> str:
    """Extract file extension from filename."""
    return filename.rsplit(".", 1)[1].lower() if "." in filename else ""


def get_collection_name(doc_category: str) -> str:
    """Map document category to vector collection name."""
    category_map = {
        "rfp": "rfps",
        "proposal": "proposals",
        "email": "emails",
        "transcript": "transcripts",
    }
    return category_map.get(doc_category.lower(), "general")


async def process_document_background(
    document_id: str,
    file_path: str,
    doc_category: str,
    db: Session,
):
    """Process document in background: extract text, update metadata, and index in vector store."""
    logger.info("Processing document %s (type=%s, category=%s)", document_id, get_file_extension(file_path), doc_category)
    try:
        file_ext = get_file_extension(file_path)

        extracted_text = None
        extraction_metadata = {}

        if file_ext == "pdf":
            result = pdf_extractor.extract(file_path)
            extracted_text = result.get("text", "")
            extraction_metadata = {k: v for k, v in result.items() if k != "text"}
        elif file_ext == "docx":
            result = docx_extractor.extract(file_path)
            extracted_text = result.get("text", "")
            extraction_metadata = {k: v for k, v in result.items() if k != "text"}
        elif file_ext == "txt":
            with open(file_path, "r") as f:
                extracted_text = f.read()
            extraction_metadata = {"format": "text", "encoding": "utf-8"}
        elif file_ext == "xlsx":
            extracted_text = f"XLSX file: {file_path}"
            extraction_metadata = {"format": "xlsx", "note": "Structured data extraction not yet implemented"}

        document = db.query(Document).filter(Document.id == document_id).first()
        if document:
            document.extracted_text = extracted_text
            document.is_processed = True
            document.extraction_metadata = extraction_metadata
            db.commit()

            if extracted_text:
                logger.info("Document %s processed: %d chars extracted, indexing in RAG...", document_id, len(extracted_text))
                collection_name = get_collection_name(doc_category)
                rag_retriever.index_document(
                    text=extracted_text,
                    collection_name=collection_name,
                    document_id=document_id,
                    metadata={
                        "document_id": document_id,
                        "category": doc_category,
                        "processed_at": datetime.utcnow().isoformat(),
                    },
                )
            else:
                logger.warning("Document %s: no text extracted", document_id)

    except Exception as e:
        logger.error("Document processing failed for %s: %s", document_id, e)
        document = db.query(Document).filter(Document.id == document_id).first()
        if document:
            document.is_processed = False
            document.extraction_metadata = {"error": str(e)}
            db.commit()


@router.post("/upload", response_model=DocumentUploadResponse)
async def upload_document(
    file: UploadFile = File(...),
    deal_id: str | None = Form(None),
    doc_category: str = Form("general"),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """
    Upload document (PDF, DOCX, XLSX, TXT). Save to uploads/{deal_id}/ directory.
    Create Document record and optionally link to deal.
    """
    file_ext = get_file_extension(file.filename)

    if file_ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"File type not allowed. Allowed types: {', '.join(ALLOWED_EXTENSIONS)}",
        )

    deal_dir = os.path.join(UPLOAD_DIR, deal_id or "general")
    os.makedirs(deal_dir, exist_ok=True)

    document_id = str(uuid4())
    file_path = os.path.join(deal_dir, f"{document_id}_{file.filename}")

    async with aiofiles.open(file_path, "wb") as f:
        content = await file.read()
        await f.write(content)

    document = Document(
        id=document_id,
        deal_id=deal_id,
        filename=file.filename,
        original_filename=file.filename,
        file_path=file_path,
        file_type=file_ext,
        file_size=len(content),
        doc_category=doc_category,
        is_processed=False,
        uploaded_by=current_user.id,
    )

    db.add(document)
    db.commit()
    db.refresh(document)

    background_tasks.add_task(process_document_background, document_id, file_path, doc_category, db)

    return DocumentUploadResponse(
        document_id=document_id,
        filename=file.filename,
        message="Document uploaded successfully. Processing will begin shortly.",
    )


@router.post("/{document_id}/process")
async def process_document(
    document_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """
    Trigger document processing. Extract text using appropriate extractor.
    Update document's extracted_text, is_processed, extraction_metadata.
    Also chunk and index in vector store via rag_retriever.
    """
    document = db.query(Document).filter(Document.id == document_id).first()

    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    background_tasks.add_task(
        process_document_background,
        document_id,
        document.file_path,
        document.doc_category,
        db,
    )

    return {"status": "processing", "message": "Document processing started", "task_id": document_id}


@router.post("/create-from-text", response_model=DocumentUploadResponse)
async def create_document_from_text(
    deal_id: str = Form(...),
    doc_category: str = Form("general"),
    title: str = Form("Untitled"),
    text_content: str = Form(...),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """
    Create a document from pasted text (meeting transcripts, emails, notes).
    The text is stored directly — no file upload needed.
    """
    document_id = str(uuid4())
    safe_title = title.replace(" ", "_")[:50]
    filename = f"{safe_title}.txt"

    # Save text to a file for consistency
    deal_dir = os.path.join(UPLOAD_DIR, deal_id)
    os.makedirs(deal_dir, exist_ok=True)
    file_path = os.path.join(deal_dir, f"{document_id}_{filename}")

    async with aiofiles.open(file_path, "w") as f:
        await f.write(text_content)

    document = Document(
        id=document_id,
        deal_id=deal_id,
        filename=filename,
        original_filename=filename,
        file_path=file_path,
        file_type="txt",
        file_size=len(text_content.encode("utf-8")),
        doc_category=doc_category,
        is_processed=True,
        extracted_text=text_content,
        extraction_metadata={"format": "text", "source": "user_input", "title": title},
        uploaded_by=current_user.id,
    )

    db.add(document)
    db.commit()
    db.refresh(document)

    # Index in vector store
    if text_content.strip():
        collection_name = get_collection_name(doc_category)
        try:
            rag_retriever.index_document(
                text=text_content,
                collection_name=collection_name,
                document_id=document_id,
                metadata={
                    "document_id": document_id,
                    "category": doc_category,
                    "title": title,
                    "processed_at": datetime.utcnow().isoformat(),
                },
            )
        except Exception as e:
            logger.warning("RAG indexing failed for text doc (non-fatal): %s", e)

    return DocumentUploadResponse(
        document_id=document_id,
        filename=filename,
        message=f"Text document '{title}' created and indexed.",
    )


@router.get("/", response_model=list[DocumentResponse])
def list_documents(
    deal_id: str | None = Query(None),
    doc_category: str | None = Query(None),
    is_processed: bool | None = Query(None),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """
    List all documents with optional filters.
    """
    query = db.query(Document)

    if deal_id:
        query = query.filter(Document.deal_id == deal_id)

    if doc_category:
        query = query.filter(Document.doc_category == doc_category)

    if is_processed is not None:
        query = query.filter(Document.is_processed == is_processed)

    documents = query.all()

    return [DocumentResponse.model_validate(doc) for doc in documents]


@router.get("/{document_id}", response_model=DocumentResponse)
def get_document(
    document_id: str,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """
    Get document detail including extracted_text.
    """
    document = db.query(Document).filter(Document.id == document_id).first()

    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    return DocumentResponse.model_validate(document)


@router.delete("/{document_id}")
def delete_document(
    document_id: str,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """
    Delete document and its chunks.
    """
    document = db.query(Document).filter(Document.id == document_id).first()

    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    db.query(DocumentChunk).filter(DocumentChunk.document_id == document_id).delete()

    if os.path.exists(document.file_path):
        os.remove(document.file_path)

    db.delete(document)
    db.commit()

    return {"message": "Document deleted successfully"}


@router.get("/{document_id}/chunks", response_model=list[ChunkResponse])
def get_document_chunks(
    document_id: str,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """
    List chunks for a processed document.
    """
    document = db.query(Document).filter(Document.id == document_id).first()

    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    chunks = db.query(DocumentChunk).filter(DocumentChunk.document_id == document_id).all()

    return [ChunkResponse.model_validate(chunk) for chunk in chunks]
