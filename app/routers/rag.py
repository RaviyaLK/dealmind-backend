from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel
from app.database import get_db
from app.services.auth import get_current_user
from app.rag.retriever import rag_retriever

router = APIRouter(prefix="/api/rag", tags=["RAG Knowledge Base"])


class RAGQueryRequest(BaseModel):
    query: str
    collection: str = "proposals"
    n_results: int = 5


class RAGQueryResult(BaseModel):
    document_id: str
    content: str
    relevance_score: float
    metadata: dict


class RAGQueryResponse(BaseModel):
    query: str
    collection: str
    results: list[RAGQueryResult]
    count: int


class RAGStatsResponse(BaseModel):
    collections: dict


@router.get("/stats", response_model=RAGStatsResponse)
def get_rag_stats(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """
    Get vector store stats (document counts per collection).
    """
    try:
        stats = rag_retriever.get_stats()
        return RAGStatsResponse(collections=stats)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving stats: {str(e)}")


@router.post("/query", response_model=RAGQueryResponse)
def query_knowledge_base(
    request: RAGQueryRequest,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """
    Query the knowledge base.
    Takes: query (str), collection (str, default "proposals"), n_results (int, default 5).
    Returns matching documents with relevance scores.
    """
    try:
        results = rag_retriever.query(
            query_text=request.query,
            collection_name=request.collection,
            n_results=request.n_results,
        )

        formatted_results = []
        for result in results:
            formatted_results.append(
                RAGQueryResult(
                    document_id=result.get("id", ""),
                    content=result.get("content", ""),
                    relevance_score=result.get("score", 0.0),
                    metadata=result.get("metadata", {}),
                )
            )

        return RAGQueryResponse(
            query=request.query,
            collection=request.collection,
            results=formatted_results,
            count=len(formatted_results),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error querying knowledge base: {str(e)}")


@router.delete("/collection/{collection_name}")
def clear_collection(
    collection_name: str,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """
    Clear a collection for re-indexing.
    """
    try:
        rag_retriever.clear_collection(collection_name)
        return {"message": f"Collection '{collection_name}' cleared successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error clearing collection: {str(e)}")
