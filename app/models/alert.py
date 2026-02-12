import uuid
from datetime import datetime
from sqlalchemy import Column, String, Text, Float, Integer, Boolean, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    deal_id: Mapped[str] = mapped_column(String(36), ForeignKey("deals.id"), nullable=False)
    alert_type: Mapped[str] = mapped_column(String(50), nullable=False)
    severity: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    source_context: Mapped[str] = mapped_column(Text, nullable=True)
    sentiment_score: Mapped[float] = mapped_column(Float, nullable=True)
    email_subject: Mapped[str] = mapped_column(String(500), nullable=True)
    email_body: Mapped[str] = mapped_column(Text, nullable=True)
    is_resolved: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    resolved_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)

    # Relationships
    deal = relationship("Deal", back_populates="alerts")
    recovery_actions = relationship("RecoveryAction", back_populates="alert", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Alert(id={self.id}, deal_id={self.deal_id}, alert_type={self.alert_type})>"


class RecoveryAction(Base):
    __tablename__ = "recovery_actions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    alert_id: Mapped[str] = mapped_column(String(36), ForeignKey("alerts.id"), nullable=False)
    action_text: Mapped[str] = mapped_column(Text, nullable=False)
    is_completed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)

    # Relationships
    alert = relationship("Alert", back_populates="recovery_actions")

    def __repr__(self):
        return f"<RecoveryAction(id={self.id}, alert_id={self.alert_id}, priority={self.priority})>"
