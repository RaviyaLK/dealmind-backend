from pydantic import BaseModel
from datetime import datetime
from typing import Optional, List, Any


class ProposalCreate(BaseModel):
    deal_id: str
    title: Optional[str] = None


class ProposalResponse(BaseModel):
    id: str
    deal_id: str
    title: str
    content: Optional[str] = None
    status: str
    version: int = 1
    compliance_score: Optional[float] = None
    compliance_notes: Optional[List[Any]] = None
    review_notes: Optional[str] = None
    generated_by: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ProposalReview(BaseModel):
    status: str
    review_notes: Optional[str] = None


class ProposalExportRequest(BaseModel):
    format: str = "docx"
