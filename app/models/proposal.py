import uuid
from datetime import datetime
from sqlalchemy import Column, String, Text, Float, Integer, DateTime, ForeignKey, JSON, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class Proposal(Base):
    __tablename__ = "proposals"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    deal_id: Mapped[str] = mapped_column(String(36), ForeignKey("deals.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    compliance_score: Mapped[float] = mapped_column(Float, nullable=True)
    compliance_notes: Mapped[dict] = mapped_column(JSON, nullable=True)
    generated_by: Mapped[str] = mapped_column(String(255), nullable=False)
    reviewed_by: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=True)
    review_notes: Mapped[str] = mapped_column(Text, nullable=True)
    file_path: Mapped[str] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    deal = relationship("Deal", back_populates="proposals")

    def __repr__(self):
        return f"<Proposal(id={self.id}, deal_id={self.deal_id}, title={self.title}, version={self.version})>"
