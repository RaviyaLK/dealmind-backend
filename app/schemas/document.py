from pydantic import BaseModel
from datetime import datetime
from typing import Optional, Dict, Any


class DocumentResponse(BaseModel):
    id: str
    deal_id: Optional[str] = None
    filename: str
    original_filename: str
    file_type: Optional[str] = None
    file_size: int
    doc_category: str
    is_processed: bool
    extracted_text: Optional[str] = None
    extraction_metadata: Optional[Dict[str, Any]] = None
    page_count: Optional[int] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class DocumentUploadResponse(BaseModel):
    document_id: str
    filename: str
    message: str


class ChunkResponse(BaseModel):
    id: str
    chunk_index: int
    chunk_text: str
    metadata_: Optional[Dict[str, Any]] = None

    model_config = {"from_attributes": True}
