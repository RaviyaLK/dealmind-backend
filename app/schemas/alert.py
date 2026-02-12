from pydantic import BaseModel
from datetime import datetime
from typing import Optional, List


class RecoveryActionResponse(BaseModel):
    id: str
    alert_id: str
    action_text: str
    is_completed: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class AlertResponse(BaseModel):
    id: str
    deal_id: str
    alert_type: str
    severity: str
    title: str
    description: str
    sentiment_score: Optional[float] = None
    source_context: Optional[str] = None
    email_subject: Optional[str] = None
    email_body: Optional[str] = None
    is_resolved: bool
    created_at: datetime
    recovery_actions: List[RecoveryActionResponse] = []

    model_config = {"from_attributes": True}


class AlertUpdate(BaseModel):
    is_resolved: Optional[bool] = None
    severity: Optional[str] = None
    email_subject: Optional[str] = None
    email_body: Optional[str] = None


class RecoveryActionUpdate(BaseModel):
    is_completed: bool
