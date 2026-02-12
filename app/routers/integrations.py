"""Google Gmail & Calendar OAuth integration endpoints."""
import logging
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from uuid import uuid4
from typing import Optional

from app.database import get_db
from app.config import settings

logger = logging.getLogger(__name__)
from app.services.auth import get_current_user
from app.models.integration import OAuthToken
from app.services.graph_api import (
    get_auth_url,
    exchange_code_for_tokens,
    refresh_access_token,
    GmailClient,
)

router = APIRouter(prefix="/api/integrations", tags=["Integrations"])


# ── OAuth Flow ──


@router.get("/google/auth")
def google_auth_redirect(
    current_user=Depends(get_current_user),
):
    """Get Google OAuth authorization URL. Frontend opens this to start the login flow."""
    if not settings.GOOGLE_CLIENT_ID:
        raise HTTPException(status_code=400, detail="Google OAuth not configured. Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET in .env")

    state = current_user.id
    auth_url = get_auth_url(state=state)
    return {"auth_url": auth_url}


@router.get("/google/callback")
async def google_callback(
    code: str = Query(...),
    state: str = Query(""),
    error: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """
    OAuth callback — Google redirects here after user grants consent.
    Exchanges code for tokens, stores them, and redirects to frontend.
    """
    if error:
        redirect_url = f"{settings.GOOGLE_FRONTEND_REDIRECT}?error={error}"
        return RedirectResponse(url=redirect_url)

    try:
        # Exchange authorization code for tokens
        tokens = await exchange_code_for_tokens(code)

        # Get user profile
        gmail = GmailClient(tokens["access_token"])
        profile = await gmail.get_me()

        user_id = state  # We passed user_id as state

        # Upsert OAuth token record
        existing = (
            db.query(OAuthToken)
            .filter(OAuthToken.user_id == user_id, OAuthToken.provider == "google")
            .first()
        )

        expires_at = datetime.utcnow() + timedelta(seconds=tokens.get("expires_in", 3600))

        if existing:
            existing.access_token = tokens["access_token"]
            existing.refresh_token = tokens.get("refresh_token") or existing.refresh_token
            existing.scope = tokens.get("scope", "")
            existing.expires_at = expires_at
            existing.account_email = profile.get("email", "")
            existing.account_name = profile.get("name", "")
            existing.updated_at = datetime.utcnow()
        else:
            oauth_token = OAuthToken(
                id=str(uuid4()),
                user_id=user_id,
                provider="google",
                access_token=tokens["access_token"],
                refresh_token=tokens.get("refresh_token"),
                token_type=tokens.get("token_type", "Bearer"),
                scope=tokens.get("scope", ""),
                expires_at=expires_at,
                account_email=profile.get("email", ""),
                account_name=profile.get("name", ""),
            )
            db.add(oauth_token)

        db.commit()

        redirect_url = f"{settings.GOOGLE_FRONTEND_REDIRECT}?gmail=connected"
        return RedirectResponse(url=redirect_url)

    except Exception as e:
        logger.error("Google callback error: %s", e)
        import traceback
        traceback.print_exc()
        redirect_url = f"{settings.GOOGLE_FRONTEND_REDIRECT}?error=token_exchange_failed&error_description={str(e)[:200]}"
        return RedirectResponse(url=redirect_url)


@router.get("/google/status")
def google_status(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Check if the user has connected their Google/Gmail account."""
    token = (
        db.query(OAuthToken)
        .filter(OAuthToken.user_id == current_user.id, OAuthToken.provider == "google")
        .first()
    )

    if not token:
        return {"connected": False}

    return {
        "connected": True,
        "account_email": token.account_email,
        "account_name": token.account_name,
        "expires_at": token.expires_at.isoformat() if token.expires_at else None,
        "is_expired": token.is_expired(),
        "connected_at": token.created_at.isoformat() if token.created_at else None,
    }


@router.delete("/google/disconnect")
def google_disconnect(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Disconnect Google/Gmail integration."""
    token = (
        db.query(OAuthToken)
        .filter(OAuthToken.user_id == current_user.id, OAuthToken.provider == "google")
        .first()
    )

    if token:
        db.delete(token)
        db.commit()

    return {"status": "disconnected"}


# ── Helper to get a valid Gmail client ──


async def get_gmail_client(user_id: str, db: Session) -> Optional[GmailClient]:
    """Get a Gmail client with a valid access token for the user. Auto-refreshes if expired."""
    token = (
        db.query(OAuthToken)
        .filter(OAuthToken.user_id == user_id, OAuthToken.provider == "google")
        .first()
    )

    if not token:
        return None

    # Refresh if expired
    if token.is_expired() and token.refresh_token:
        try:
            new_tokens = await refresh_access_token(token.refresh_token)
            token.access_token = new_tokens["access_token"]
            token.refresh_token = new_tokens.get("refresh_token", token.refresh_token)
            token.expires_at = datetime.utcnow() + timedelta(seconds=new_tokens.get("expires_in", 3600))
            token.updated_at = datetime.utcnow()
            db.commit()
        except Exception as e:
            logger.warning("Token refresh failed: %s", e)
            return None

    return GmailClient(token.access_token)


# ── Email endpoints ──


@router.get("/google/emails")
async def get_emails(
    days: int = Query(7, ge=1, le=90),
    search: Optional[str] = Query(None),
    top: int = Query(20, ge=1, le=50),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Fetch recent emails from the connected Gmail account."""
    gmail = await get_gmail_client(current_user.id, db)
    if not gmail:
        raise HTTPException(status_code=400, detail="Gmail not connected. Please connect your Google account first.")

    try:
        if search:
            emails = await gmail.search_emails(query=search, max_results=top)
        else:
            emails = await gmail.get_recent_emails(days=days, max_results=top)
        return emails
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Failed to fetch emails: {str(e)}")


@router.post("/google/send-email")
async def send_email(
    request: dict,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Send an email through the connected Gmail account (for recovery emails)."""
    gmail = await get_gmail_client(current_user.id, db)
    if not gmail:
        raise HTTPException(status_code=400, detail="Gmail not connected")

    to = request.get("to", [])
    subject = request.get("subject", "")
    body = request.get("body", "")
    cc = request.get("cc", [])

    if not to or not subject:
        raise HTTPException(status_code=400, detail="'to' and 'subject' are required")

    try:
        result = await gmail.send_email(to=to, subject=subject, body=body, cc=cc)
        return result
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Failed to send email: {str(e)}")


@router.get("/google/calendar")
async def get_calendar(
    days_ahead: int = Query(14, ge=1, le=60),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Fetch upcoming calendar events from the connected Google Calendar."""
    gmail = await get_gmail_client(current_user.id, db)
    if not gmail:
        raise HTTPException(status_code=400, detail="Gmail not connected")

    try:
        events = await gmail.get_calendar_events(days_ahead=days_ahead)
        return events
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Failed to fetch calendar: {str(e)}")
