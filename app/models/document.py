import uuid
from datetime import datetime
from sqlalchemy import Column, String, Text, Integer, Boolean, DateTime, ForeignKey, JSON, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    deal_id: Mapped[str] = mapped_column(String(36), ForeignKey("deals.id"), nullable=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    file_type: Mapped[str] = mapped_column(String(50), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    doc_category: Mapped[str] = mapped_column(String(50), nullable=False)
    is_processed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    extracted_text: Mapped[str] = mapped_column(Text, nullable=True)
    extraction_metadata: Mapped[dict] = mapped_column(JSON, nullable=True)
    page_count: Mapped[int] = mapped_column(Integer, nullable=True)
    uploaded_by: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)

    # Relationships
    deal = relationship("Deal", back_populates="documents")
    chunks = relationship("DocumentChunk", back_populates="document", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Document(id={self.id}, filename={self.filename}, deal_id={self.deal_id})>"


class DocumentChunk(Base):
    __tablename__ = "document_chunks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    document_id: Mapped[str] = mapped_column(String(36), ForeignKey("documents.id"), nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    chunk_text: Mapped[str] = mapped_column(Text, nullable=False)
    embedding_id: Mapped[str] = mapped_column(String(255), nullable=True)
    metadata_: Mapped[dict] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)

    # Relationships
    document = relationship("Document", back_populates="chunks")

    def __repr__(self):
        return f"<DocumentChunk(id={self.id}, document_id={self.document_id}, chunk_index={self.chunk_index})>"
