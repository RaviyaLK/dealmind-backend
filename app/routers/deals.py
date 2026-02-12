from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from uuid import uuid4
from app.database import get_db
from app.services.auth import get_current_user
from app.models.deal import Deal, DealRequirement, DealAnalysis
from app.models.alert import Alert
from app.models.document import Document
from app.schemas.deal import (
    DealCreate,
    DealUpdate,
    DealResponse,
    DealListResponse,
    DealRequirementResponse,
    DealAnalysisResponse,
)
from app.schemas.alert import AlertResponse
from app.schemas.document import DocumentResponse

router = APIRouter(prefix="/api/deals", tags=["Deals"])


@router.get("/", response_model=DealListResponse)
def list_deals(
    stage: str | None = Query(None),
    status: str | None = Query(None),
    search: str | None = Query(None),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """
    List all deals with optional filters.
    """
    query = db.query(Deal).filter(Deal.owner_id == current_user.id)

    if stage:
        query = query.filter(Deal.stage == stage)

    if status:
        query = query.filter(Deal.status == status)

    if search:
        query = query.filter(
            (Deal.title.ilike(f"%{search}%")) | (Deal.description.ilike(f"%{search}%"))
        )

    deals = query.all()

    deal_responses = []
    for deal in deals:
        requirement_count = db.query(DealRequirement).filter(
            DealRequirement.deal_id == deal.id
        ).count()
        document_count = db.query(Document).filter(
            Document.deal_id == deal.id
        ).count()
        alert_count = db.query(Alert).filter(Alert.deal_id == deal.id).count()

        deal_dict = {c.key: getattr(deal, c.key) for c in deal.__table__.columns}
        deal_dict["requirement_count"] = requirement_count
        deal_dict["document_count"] = document_count
        deal_dict["alert_count"] = alert_count
        deal_responses.append(DealResponse(**deal_dict))

    return DealListResponse(deals=deal_responses, total=len(deal_responses))


@router.post("/", response_model=DealResponse)
def create_deal(
    deal_data: DealCreate,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """
    Create a new deal. Sets owner_id from current user.
    """
    deal_id = str(uuid4())
    deal = Deal(
        id=deal_id,
        owner_id=current_user.id,
        title=deal_data.title,
        client_name=deal_data.client_name,
        deal_value=deal_data.deal_value,
        description=deal_data.description,
        source=deal_data.source,
    )

    db.add(deal)
    db.commit()
    db.refresh(deal)

    deal_dict = {c.key: getattr(deal, c.key) for c in deal.__table__.columns}
    deal_dict["requirement_count"] = 0
    deal_dict["document_count"] = 0
    deal_dict["alert_count"] = 0
    return DealResponse(**deal_dict)


@router.get("/{deal_id}", response_model=DealResponse)
def get_deal(
    deal_id: str,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """
    Get deal by ID with all related data.
    """
    deal = db.query(Deal).filter(Deal.id == deal_id).first()

    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")

    if deal.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to access this deal")

    requirement_count = db.query(DealRequirement).filter(
        DealRequirement.deal_id == deal.id
    ).count()
    document_count = db.query(Document).filter(Document.deal_id == deal.id).count()
    alert_count = db.query(Alert).filter(Alert.deal_id == deal.id).count()

    deal_dict = {c.key: getattr(deal, c.key) for c in deal.__table__.columns}
    deal_dict["requirement_count"] = requirement_count
    deal_dict["document_count"] = document_count
    deal_dict["alert_count"] = alert_count
    return DealResponse(**deal_dict)


@router.patch("/{deal_id}", response_model=DealResponse)
def update_deal(
    deal_id: str,
    deal_data: DealUpdate,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """
    Update deal fields.
    """
    deal = db.query(Deal).filter(Deal.id == deal_id).first()

    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")

    if deal.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to update this deal")

    update_data = deal_data.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(deal, field, value)

    db.commit()
    db.refresh(deal)

    requirement_count = db.query(DealRequirement).filter(
        DealRequirement.deal_id == deal.id
    ).count()
    document_count = db.query(Document).filter(Document.deal_id == deal.id).count()
    alert_count = db.query(Alert).filter(Alert.deal_id == deal.id).count()

    deal_dict = {c.key: getattr(deal, c.key) for c in deal.__table__.columns}
    deal_dict["requirement_count"] = requirement_count
    deal_dict["document_count"] = document_count
    deal_dict["alert_count"] = alert_count
    return DealResponse(**deal_dict)


@router.delete("/{deal_id}")
def delete_deal(
    deal_id: str,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """
    Delete deal (soft delete by setting status to 'closed').
    """
    deal = db.query(Deal).filter(Deal.id == deal_id).first()

    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")

    if deal.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to delete this deal")

    deal.status = "closed"
    db.commit()

    return {"message": "Deal closed successfully"}


@router.get("/{deal_id}/requirements", response_model=list[DealRequirementResponse])
def get_deal_requirements(
    deal_id: str,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """
    List requirements for a deal.
    """
    deal = db.query(Deal).filter(Deal.id == deal_id).first()

    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")

    if deal.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to access this deal")

    requirements = db.query(DealRequirement).filter(
        DealRequirement.deal_id == deal_id
    ).all()

    return [DealRequirementResponse.model_validate(req) for req in requirements]


@router.get("/{deal_id}/analysis", response_model=DealAnalysisResponse)
def get_deal_analysis(
    deal_id: str,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """
    Get latest analysis for a deal.
    """
    deal = db.query(Deal).filter(Deal.id == deal_id).first()

    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")

    if deal.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to access this deal")

    analysis = (
        db.query(DealAnalysis)
        .filter(DealAnalysis.deal_id == deal_id)
        .order_by(DealAnalysis.created_at.desc())
        .first()
    )

    if not analysis:
        raise HTTPException(status_code=404, detail="No analysis found for this deal")

    return DealAnalysisResponse.model_validate(analysis)


@router.get("/{deal_id}/alerts", response_model=list[AlertResponse])
def get_deal_alerts(
    deal_id: str,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """
    List alerts for a deal.
    """
    deal = db.query(Deal).filter(Deal.id == deal_id).first()

    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")

    if deal.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to access this deal")

    alerts = db.query(Alert).filter(Alert.deal_id == deal_id).all()

    return [AlertResponse.model_validate(alert) for alert in alerts]


@router.get("/{deal_id}/documents", response_model=list[DocumentResponse])
def get_deal_documents(
    deal_id: str,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """
    List documents for a deal.
    """
    deal = db.query(Deal).filter(Deal.id == deal_id).first()

    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")

    if deal.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to access this deal")

    documents = db.query(Document).filter(Document.deal_id == deal_id).all()

    return [DocumentResponse.model_validate(doc) for doc in documents]
