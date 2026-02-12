from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc
from app.database import get_db
from app.services.auth import get_current_user
from app.models.alert import Alert, RecoveryAction
from app.schemas.alert import AlertResponse, AlertUpdate, RecoveryActionUpdate
from pydantic import BaseModel

router = APIRouter(prefix="/api/alerts", tags=["Alerts"])


class AlertSummaryResponse(BaseModel):
    count_by_severity: dict
    count_by_type: dict
    count_unresolved: int


@router.get("/", response_model=list[AlertResponse])
def list_alerts(
    deal_id: str | None = Query(None),
    severity: str | None = Query(None),
    is_resolved: bool | None = Query(None),
    alert_type: str | None = Query(None),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """
    List alerts with optional filters. Order by created_at descending.
    """
    query = db.query(Alert).order_by(desc(Alert.created_at))

    if deal_id:
        query = query.filter(Alert.deal_id == deal_id)

    if severity:
        query = query.filter(Alert.severity == severity)

    if is_resolved is not None:
        query = query.filter(Alert.is_resolved == is_resolved)

    if alert_type:
        query = query.filter(Alert.alert_type == alert_type)

    alerts = query.all()

    return [AlertResponse.model_validate(alert) for alert in alerts]


# IMPORTANT: /summary must come BEFORE /{alert_id} so FastAPI doesn't
# match "summary" as an alert_id parameter.
@router.get("/summary", response_model=AlertSummaryResponse)
def get_alert_summary(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """
    Get alert summary (count by severity, count by type, count unresolved).
    """
    all_alerts = db.query(Alert).all()

    count_by_severity = {}
    count_by_type = {}
    count_unresolved = 0

    for alert in all_alerts:
        if alert.severity not in count_by_severity:
            count_by_severity[alert.severity] = 0
        count_by_severity[alert.severity] += 1

        if alert.alert_type not in count_by_type:
            count_by_type[alert.alert_type] = 0
        count_by_type[alert.alert_type] += 1

        if not alert.is_resolved:
            count_unresolved += 1

    return AlertSummaryResponse(
        count_by_severity=count_by_severity,
        count_by_type=count_by_type,
        count_unresolved=count_unresolved,
    )


@router.get("/{alert_id}", response_model=AlertResponse)
def get_alert(
    alert_id: str,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """
    Get alert with recovery actions.
    """
    alert = db.query(Alert).filter(Alert.id == alert_id).first()

    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")

    return AlertResponse.model_validate(alert)


@router.patch("/{alert_id}", response_model=AlertResponse)
def update_alert(
    alert_id: str,
    alert_data: AlertUpdate,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """
    Update alert (resolve, change severity).
    """
    alert = db.query(Alert).filter(Alert.id == alert_id).first()

    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")

    update_data = alert_data.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(alert, field, value)

    db.commit()
    db.refresh(alert)

    return AlertResponse.model_validate(alert)


@router.patch("/{alert_id}/actions/{action_id}")
def toggle_recovery_action(
    alert_id: str,
    action_id: str,
    action_data: RecoveryActionUpdate,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """
    Toggle recovery action completion.
    """
    alert = db.query(Alert).filter(Alert.id == alert_id).first()

    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")

    action = db.query(RecoveryAction).filter(RecoveryAction.id == action_id).first()

    if not action or action.alert_id != alert_id:
        raise HTTPException(status_code=404, detail="Recovery action not found")

    update_data = action_data.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(action, field, value)

    db.commit()
    db.refresh(action)

    return {
        "action_id": action.id,
        "is_completed": action.is_completed,
        "message": "Recovery action updated successfully",
    }


@router.delete("/deal/{deal_id}")
def clear_alerts_for_deal(
    deal_id: str,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Clear all alerts (and their recovery actions) for a specific deal.
    Used to reset monitoring state before re-running the agent.
    """
    alerts = db.query(Alert).filter(Alert.deal_id == deal_id).all()
    if not alerts:
        return {"deleted": 0, "message": "No alerts to clear"}

    count = len(alerts)
    for alert in alerts:
        # Delete child recovery actions first
        db.query(RecoveryAction).filter(RecoveryAction.alert_id == alert.id).delete()
        db.delete(alert)

    db.commit()
    return {"deleted": count, "message": f"Cleared {count} alert(s) for this deal"}
