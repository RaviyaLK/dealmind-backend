import uuid
from datetime import datetime
from sqlalchemy import Column, String, Integer, Float, Boolean, DateTime, JSON, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class Employee(Base):
    __tablename__ = "employees"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(255), nullable=False)
    department: Mapped[str] = mapped_column(String(255), nullable=False)
    skills: Mapped[dict] = mapped_column(JSON, nullable=True)
    availability_percent: Mapped[int] = mapped_column(Integer, nullable=False)
    hourly_rate: Mapped[float] = mapped_column(Float, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    uploaded_from: Mapped[str] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    assignments = relationship("DealAssignment", back_populates="employee", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Employee(id={self.id}, name={self.name}, email={self.email})>"
