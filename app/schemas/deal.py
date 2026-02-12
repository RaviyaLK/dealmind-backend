from pydantic import BaseModel
from datetime import datetime
from typing import Optional, List


class DealCreate(BaseModel):
    title: str
    client_name: str
    deal_value: float
    description: Optional[str] = None
    source: Optional[str] = "manual"


class DealUpdate(BaseModel):
    title: Optional[str] = None
    client_name: Optional[str] = None
    deal_value: Optional[float] = None
    stage: Optional[str] = None
    health_score: Optional[float] = None
    status: Optional[str] = None
    description: Optional[str] = None


class DealResponse(BaseModel):
    id: str
    title: str
    client_name: str
    deal_value: float
    stage: str
    health_score: float
    status: str
    description: Optional[str]
    source: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    requirement_count: int = 0
    document_count: int = 0
    alert_count: int = 0

    model_config = {"from_attributes": True}


class DealListResponse(BaseModel):
    deals: List[DealResponse]
    total: int


class DealRequirementResponse(BaseModel):
    id: str
    deal_id: str
    category: str
    requirement_text: str
    confidence: float
    is_met: Optional[bool] = None
    matched_by: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class DealAnalysisResponse(BaseModel):
    id: str
    deal_id: str
    analysis_type: str
    recommendation: str
    confidence_score: float
    positive_factors: Optional[List] = None
    risk_factors: Optional[List] = None
    conditions: Optional[List] = None
    reasoning: str
    created_at: datetime

    model_config = {"from_attributes": True}
