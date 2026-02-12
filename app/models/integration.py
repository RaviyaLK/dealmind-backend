"""OAuth integration tokens model — stores Google OAuth credentials per user."""
import uuid
from datetime import datetime
from sqlalchemy import String, Text, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class OAuthToken(Base):
    __tablename__ = "oauth_tokens"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False)
    provider: Mapped[str] = mapped_column(String(50), nullable=False, default="google")  # "google", etc.
    access_token: Mapped[str] = mapped_column(Text, nullable=False)
    refresh_token: Mapped[str] = mapped_column(Text, nullable=True)
    token_type: Mapped[str] = mapped_column(String(50), nullable=False, default="Bearer")
    scope: Mapped[str] = mapped_column(Text, nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    account_email: Mapped[str] = mapped_column(String(255), nullable=True)
    account_name: Mapped[str] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", backref="oauth_tokens")

    def is_expired(self) -> bool:
        if not self.expires_at:
            return True
        return datetime.utcnow() >= self.expires_at
