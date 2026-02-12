import uuid
from datetime import datetime
from sqlalchemy import Column, String, Text, Float, Integer, DateTime, ForeignKey, JSON, func, Enum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class Deal(Base):
    __tablename__ = "deals"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    client_name: Mapped[str] = mapped_column(String(255), nullable=False)
    deal_value: Mapped[float] = mapped_column(Float, nullable=False)
    stage: Mapped[str] = mapped_column(String(50), nullable=False, default="discovery")
    health_score: Mapped[int] = mapped_column(Integer, nullable=False, default=70)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="active")
    owner_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)
    closed_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    description: Mapped[str] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(String(255), nullable=True)

    # Relationships
    requirements = relationship("DealRequirement", back_populates="deal", cascade="all, delete-orphan")
    documents = relationship("Document", back_populates="deal", cascade="all, delete-orphan")
    alerts = relationship("Alert", back_populates="deal", cascade="all, delete-orphan")
    analysis_results = relationship("DealAnalysis", back_populates="deal", cascade="all, delete-orphan")
    proposals = relationship("Proposal", back_populates="deal", cascade="all, delete-orphan")
    assignments = relationship("DealAssignment", back_populates="deal", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Deal(id={self.id}, title={self.title}, client_name={self.client_name})>"


class DealRequirement(Base):
    __tablename__ = "deal_requirements"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    deal_id: Mapped[str] = mapped_column(String(36), ForeignKey("deals.id"), nullable=False)
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    requirement_text: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    is_met: Mapped[bool] = mapped_column(nullable=True)
    matched_by: Mapped[str] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)

    # Relationships
    deal = relationship("Deal", back_populates="requirements")

    def __repr__(self):
        return f"<DealRequirement(id={self.id}, deal_id={self.deal_id}, category={self.category})>"


class DealAnalysis(Base):
    __tablename__ = "deal_analysis"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    deal_id: Mapped[str] = mapped_column(String(36), ForeignKey("deals.id"), nullable=False)
    analysis_type: Mapped[str] = mapped_column(String(50), nullable=False)
    recommendation: Mapped[str] = mapped_column(String(50), nullable=False)
    confidence_score: Mapped[float] = mapped_column(Float, nullable=False)
    positive_factors: Mapped[dict] = mapped_column(JSON, nullable=True)
    risk_factors: Mapped[dict] = mapped_column(JSON, nullable=True)
    conditions: Mapped[dict] = mapped_column(JSON, nullable=True)
    reasoning: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)

    # Relationships
    deal = relationship("Deal", back_populates="analysis_results")

    def __repr__(self):
        return f"<DealAnalysis(id={self.id}, deal_id={self.deal_id}, analysis_type={self.analysis_type})>"
