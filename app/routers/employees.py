from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from sqlalchemy.orm import Session
from sqlalchemy import and_
import aiofiles
import os
from uuid import uuid4
from app.database import get_db
from app.services.auth import get_current_user
from app.models.employee import Employee
from app.models.deal import Deal, DealRequirement
from app.schemas.employee import (
    EmployeeCreate,
    EmployeeUpdate,
    EmployeeResponse,
    EmployeeUploadResponse,
)
from app.ingestion.excel import excel_processor

router = APIRouter(prefix="/api/employees", tags=["Employees"])


@router.get("/", response_model=list[EmployeeResponse])
def list_employees(
    department: str | None = Query(None),
    role: str | None = Query(None),
    skills: str | None = Query(None),
    min_availability: int | None = Query(None),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """
    List employees with optional filters.
    """
    query = db.query(Employee)

    if department:
        query = query.filter(Employee.department == department)

    if role:
        query = query.filter(Employee.role == role)

    if min_availability is not None:
        query = query.filter(Employee.availability_percent >= min_availability)

    employees = query.all()

    if skills:
        skill_list = [s.strip().lower() for s in skills.split(",")]
        filtered_employees = []
        for emp in employees:
            if emp.skills:
                emp_skills = [s.lower() for s in emp.skills]
                if any(skill in emp_skills for skill in skill_list):
                    filtered_employees.append(emp)
        employees = filtered_employees

    return [EmployeeResponse.model_validate(emp) for emp in employees]


@router.post("/", response_model=EmployeeResponse)
def create_employee(
    employee_data: EmployeeCreate,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """
    Create single employee manually.
    """
    employee_id = str(uuid4())
    employee = Employee(
        id=employee_id,
        name=employee_data.name,
        email=employee_data.email,
        department=employee_data.department,
        role=employee_data.role,
        skills=employee_data.skills,
        availability_percent=employee_data.availability_percent,
        hourly_rate=employee_data.hourly_rate,
    )

    db.add(employee)
    db.commit()
    db.refresh(employee)

    return EmployeeResponse.model_validate(employee)


@router.post("/upload", response_model=EmployeeUploadResponse)
async def upload_employees(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """
    Upload Excel file to bulk import employees.
    """
    upload_dir = "uploads/employees"
    os.makedirs(upload_dir, exist_ok=True)

    file_path = os.path.join(upload_dir, file.filename)

    async with aiofiles.open(file_path, "wb") as f:
        content = await file.read()
        await f.write(content)

    imported, skipped, errors = excel_processor.process_employee_excel(file_path, db, file.filename)

    return EmployeeUploadResponse(
        total_imported=imported,
        total_skipped=skipped,
        errors=errors,
    )


@router.get("/{employee_id}", response_model=EmployeeResponse)
def get_employee(
    employee_id: str,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """
    Get single employee.
    """
    employee = db.query(Employee).filter(Employee.id == employee_id).first()

    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")

    return EmployeeResponse.model_validate(employee)


@router.patch("/{employee_id}", response_model=EmployeeResponse)
def update_employee(
    employee_id: str,
    employee_data: EmployeeUpdate,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """
    Update employee.
    """
    employee = db.query(Employee).filter(Employee.id == employee_id).first()

    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")

    update_data = employee_data.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(employee, field, value)

    db.commit()
    db.refresh(employee)

    return EmployeeResponse.model_validate(employee)


@router.delete("/{employee_id}")
def delete_employee(
    employee_id: str,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """
    Delete employee.
    """
    employee = db.query(Employee).filter(Employee.id == employee_id).first()

    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")

    db.delete(employee)
    db.commit()

    return {"message": "Employee deleted successfully"}


@router.get("/match/{deal_id}", response_model=list[EmployeeResponse])
def match_employees_to_deal(
    deal_id: str,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """
    Match employees to deal requirements. Returns employees whose skills overlap with deal requirements.
    """
    deal = db.query(Deal).filter(Deal.id == deal_id).first()

    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")

    if deal.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to access this deal")

    requirements = db.query(DealRequirement).filter(
        DealRequirement.deal_id == deal_id
    ).all()

    if not requirements:
        return []

    required_skills = set()
    for req in requirements:
        # Extract keywords from requirement text and category
        if req.requirement_text:
            words = req.requirement_text.lower().split()
            for word in words:
                if len(word) > 3:
                    required_skills.add(word)
        if req.category:
            required_skills.add(req.category.lower())

    all_employees = db.query(Employee).all()

    matched_employees = []
    for emp in all_employees:
        if emp.skills:
            emp_skills = {s.lower() for s in emp.skills}
            matching_skills = emp_skills.intersection(required_skills)
            if matching_skills:
                matched_employees.append((emp, len(matching_skills)))

    matched_employees.sort(key=lambda x: x[1], reverse=True)

    return [EmployeeResponse.model_validate(emp[0]) for emp in matched_employees]
