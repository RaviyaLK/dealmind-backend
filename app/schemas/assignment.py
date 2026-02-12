from pydantic import BaseModel
from datetime import datetime
from typing import Optional, List


class AssignEmployeeRequest(BaseModel):
    """Assign a single employee to a deal."""
    employee_id: str
    role_on_deal: Optional[str] = None
    allocation_percent: int = 100
    hourly_rate_override: Optional[float] = None
    notes: Optional[str] = None


class AutoAssignRequest(BaseModel):
    """Auto-assign top matching employees to a deal."""
    max_employees: int = 5  # Max number of employees to auto-assign


class UpdateAssignmentRequest(BaseModel):
    """Update an existing assignment."""
    role_on_deal: Optional[str] = None
    allocation_percent: Optional[int] = None
    hourly_rate_override: Optional[float] = None
    notes: Optional[str] = None


class AssignmentResponse(BaseModel):
    """Response for a single assignment with employee details embedded."""
    id: str
    deal_id: str
    employee_id: str
    role_on_deal: Optional[str]
    allocation_percent: int
    hourly_rate_override: Optional[float]
    assigned_by: str
    match_score: Optional[int]
    notes: Optional[str]
    created_at: datetime
    updated_at: datetime

    # Embedded employee info (populated at response time)
    employee_name: Optional[str] = None
    employee_email: Optional[str] = None
    employee_role: Optional[str] = None
    employee_department: Optional[str] = None
    employee_skills: Optional[List[str]] = None
    employee_availability: Optional[int] = None
    employee_hourly_rate: Optional[float] = None

    model_config = {"from_attributes": True}


class StaffingSummary(BaseModel):
    """Summary of all assignments for a deal."""
    deal_id: str
    total_assigned: int
    total_monthly_cost: float
    assignments: List[AssignmentResponse]
