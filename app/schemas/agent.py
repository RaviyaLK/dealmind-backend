from pydantic import BaseModel
from typing import Optional, Dict, Any


class AgentTaskRequest(BaseModel):
    deal_id: str
    flow_type: str


class AgentTaskResponse(BaseModel):
    task_id: str
    status: str
    message: str


class AgentStatusUpdate(BaseModel):
    task_id: str
    step: str
    step_number: int
    total_steps: int
    status: str
    message: str
    data: Optional[Dict[str, Any]] = None
