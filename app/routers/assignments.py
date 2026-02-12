from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from uuid import uuid4
from app.database import get_db
from app.services.auth import get_current_user
from app.models.deal import Deal, DealRequirement
from app.models.employee import Employee
from app.models.assignment import DealAssignment
from app.schemas.assignment import (
    AssignEmployeeRequest,
    AutoAssignRequest,
    UpdateAssignmentRequest,
    AssignmentResponse,
    StaffingSummary,
)

router = APIRouter(prefix="/api/deals", tags=["Assignments"])


def _assignment_to_response(assignment: DealAssignment) -> AssignmentResponse:
    """Convert a DealAssignment ORM object to response with embedded employee info."""
    emp = assignment.employee
    return AssignmentResponse(
        id=assignment.id,
        deal_id=assignment.deal_id,
        employee_id=assignment.employee_id,
        role_on_deal=assignment.role_on_deal,
        allocation_percent=assignment.allocation_percent,
        hourly_rate_override=assignment.hourly_rate_override,
        assigned_by=assignment.assigned_by,
        match_score=assignment.match_score,
        notes=assignment.notes,
        created_at=assignment.created_at,
        updated_at=assignment.updated_at,
        employee_name=emp.name if emp else None,
        employee_email=emp.email if emp else None,
        employee_role=emp.role if emp else None,
        employee_department=emp.department if emp else None,
        employee_skills=emp.skills if emp else None,
        employee_availability=emp.availability_percent if emp else None,
        employee_hourly_rate=emp.hourly_rate if emp else None,
    )


# ── List all assignments for a deal ──
@router.get("/{deal_id}/assignments", response_model=StaffingSummary)
def list_assignments(
    deal_id: str,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Get all employees assigned to a deal, with cost summary."""
    deal = db.query(Deal).filter(Deal.id == deal_id).first()
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")

    assignments = (
        db.query(DealAssignment)
        .filter(DealAssignment.deal_id == deal_id)
        .all()
    )

    responses = [_assignment_to_response(a) for a in assignments]

    # Calculate total monthly cost
    total_monthly = 0.0
    for a in assignments:
        rate = a.hourly_rate_override if a.hourly_rate_override is not None else a.employee.hourly_rate
        monthly = rate * 160 * (a.allocation_percent / 100)
        total_monthly += monthly

    return StaffingSummary(
        deal_id=deal_id,
        total_assigned=len(responses),
        total_monthly_cost=total_monthly,
        assignments=responses,
    )


# ── Manually assign an employee ──
@router.post("/{deal_id}/assignments", response_model=AssignmentResponse)
def assign_employee(
    deal_id: str,
    req: AssignEmployeeRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Manually assign an employee to a deal."""
    deal = db.query(Deal).filter(Deal.id == deal_id).first()
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")

    employee = db.query(Employee).filter(Employee.id == req.employee_id).first()
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")

    # Check if already assigned
    existing = (
        db.query(DealAssignment)
        .filter(DealAssignment.deal_id == deal_id, DealAssignment.employee_id == req.employee_id)
        .first()
    )
    if existing:
        raise HTTPException(status_code=409, detail="Employee already assigned to this deal")

    assignment = DealAssignment(
        id=str(uuid4()),
        deal_id=deal_id,
        employee_id=req.employee_id,
        role_on_deal=req.role_on_deal or employee.role,
        allocation_percent=req.allocation_percent,
        hourly_rate_override=req.hourly_rate_override,
        assigned_by="manual",
        notes=req.notes,
    )

    db.add(assignment)
    db.commit()
    db.refresh(assignment)

    return _assignment_to_response(assignment)


# ── Auto-assign top matching employees ──
@router.post("/{deal_id}/assignments/auto", response_model=list[AssignmentResponse])
def auto_assign(
    deal_id: str,
    req: AutoAssignRequest = AutoAssignRequest(),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Auto-assign top matching employees based on deal requirements."""
    deal = db.query(Deal).filter(Deal.id == deal_id).first()
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")

    requirements = db.query(DealRequirement).filter(DealRequirement.deal_id == deal_id).all()
    if not requirements:
        raise HTTPException(status_code=400, detail="No requirements found. Run qualification first.")

    # Build keywords from requirements
    required_skills = set()
    for r in requirements:
        if r.requirement_text:
            for word in r.requirement_text.lower().split():
                if len(word) > 3:
                    required_skills.add(word)
        if r.category:
            required_skills.add(r.category.lower())

    # Get employees not already assigned to this deal
    already_assigned_ids = {
        a.employee_id
        for a in db.query(DealAssignment).filter(DealAssignment.deal_id == deal_id).all()
    }

    all_employees = db.query(Employee).filter(Employee.is_active == True).all()

    scored = []
    for emp in all_employees:
        if emp.id in already_assigned_ids:
            continue
        if emp.skills:
            emp_skills = {s.lower() for s in emp.skills}
            emp_role_words = {w.lower() for w in emp.role.split() if len(w) > 3}
            all_terms = emp_skills | emp_role_words
            overlap = all_terms & required_skills
            if overlap:
                scored.append((emp, len(overlap)))

    scored.sort(key=lambda x: x[1], reverse=True)

    # Assign top N
    new_assignments = []
    for emp, score in scored[: req.max_employees]:
        assignment = DealAssignment(
            id=str(uuid4()),
            deal_id=deal_id,
            employee_id=emp.id,
            role_on_deal=emp.role,
            allocation_percent=min(emp.availability_percent, 100),
            assigned_by="auto",
            match_score=score,
        )
        db.add(assignment)
        new_assignments.append(assignment)

    if new_assignments:
        db.commit()
        for a in new_assignments:
            db.refresh(a)

    return [_assignment_to_response(a) for a in new_assignments]


# ── Update an assignment (allocation, role, rate, notes) ──
@router.patch("/{deal_id}/assignments/{assignment_id}", response_model=AssignmentResponse)
def update_assignment(
    deal_id: str,
    assignment_id: str,
    req: UpdateAssignmentRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Update an existing assignment's details."""
    assignment = (
        db.query(DealAssignment)
        .filter(DealAssignment.id == assignment_id, DealAssignment.deal_id == deal_id)
        .first()
    )
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")

    update_data = req.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(assignment, field, value)

    db.commit()
    db.refresh(assignment)

    return _assignment_to_response(assignment)


# ── Unassign (remove) an employee from a deal ──
@router.delete("/{deal_id}/assignments/{assignment_id}")
def unassign_employee(
    deal_id: str,
    assignment_id: str,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Remove an employee assignment from a deal."""
    assignment = (
        db.query(DealAssignment)
        .filter(DealAssignment.id == assignment_id, DealAssignment.deal_id == deal_id)
        .first()
    )
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")

    db.delete(assignment)
    db.commit()

    return {"message": "Employee unassigned successfully"}


# ── Get unassigned (available) employees for a deal ──
@router.get("/{deal_id}/available-employees")
def available_employees(
    deal_id: str,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Get employees NOT yet assigned to this deal (for the assign picker)."""
    already_assigned_ids = {
        a.employee_id
        for a in db.query(DealAssignment).filter(DealAssignment.deal_id == deal_id).all()
    }

    employees = db.query(Employee).filter(Employee.is_active == True).all()
    available = [
        {
            "id": emp.id,
            "name": emp.name,
            "role": emp.role,
            "department": emp.department,
            "skills": emp.skills or [],
            "availability_percent": emp.availability_percent,
            "hourly_rate": emp.hourly_rate,
        }
        for emp in employees
        if emp.id not in already_assigned_ids
    ]

    return available
