from pydantic import BaseModel
from datetime import datetime
from typing import Optional, List


class EmployeeCreate(BaseModel):
    name: str
    email: str
    role: str
    department: str
    skills: List[str]
    availability_percent: int
    hourly_rate: float


class EmployeeUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    role: Optional[str] = None
    department: Optional[str] = None
    skills: Optional[List[str]] = None
    availability_percent: Optional[int] = None
    hourly_rate: Optional[float] = None


class EmployeeResponse(BaseModel):
    id: str
    name: str
    email: str
    role: str
    department: str
    skills: List[str]
    availability_percent: int
    hourly_rate: float
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class EmployeeUploadResponse(BaseModel):
    total_imported: int
    total_skipped: int
    errors: List[str]
