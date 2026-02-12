import uuid
from datetime import datetime
from sqlalchemy import String, Float, Integer, DateTime, ForeignKey, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class DealAssignment(Base):
    """Junction table: assigns employees to deals with allocation details."""
    __tablename__ = "deal_assignments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    deal_id: Mapped[str] = mapped_column(String(36), ForeignKey("deals.id"), nullable=False)
    employee_id: Mapped[str] = mapped_column(String(36), ForeignKey("employees.id"), nullable=False)

    # Assignment details
    role_on_deal: Mapped[str] = mapped_column(String(255), nullable=True)  # e.g. "Lead Developer", "Data Scientist"
    allocation_percent: Mapped[int] = mapped_column(Integer, nullable=False, default=100)  # How much of their time
    hourly_rate_override: Mapped[float] = mapped_column(Float, nullable=True)  # Override employee's default rate
    assigned_by: Mapped[str] = mapped_column(String(20), nullable=False, default="manual")  # "manual" or "auto"
    match_score: Mapped[int] = mapped_column(Integer, nullable=True)  # AI match score (if auto-assigned)
    notes: Mapped[str] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    deal = relationship("Deal", back_populates="assignments")
    employee = relationship("Employee", back_populates="assignments")

    def __repr__(self):
        return f"<DealAssignment(deal_id={self.deal_id}, employee_id={self.employee_id})>"
