"""MCP Gmail Tools — Read, search, and send emails via Gmail.

Wraps the existing GmailClient from app/services/graph_api.py.
Each tool receives `user_id` and `db` (SQLAlchemy Session) via context
injection from the MCPToolRegistry. These are used to fetch the user's
OAuth token and create an authenticated GmailClient.
"""

import logging
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


async def _get_client(user_id: str, db: Session):
    """Get an authenticated GmailClient for the user.

    Reuses the existing helper from integrations router which handles
    token refresh automatically.
    """
    from app.routers.integrations import get_gmail_client
    return await get_gmail_client(user_id, db)


# ═══════════════════════════════════════════════════════════
# TOOL: read_inbox
# ═══════════════════════════════════════════════════════════

async def read_inbox(
    user_id: str,
    db: Session,
    days: int = 7,
    max_results: int = 10,
) -> dict:
    """Read recent emails from the user's Gmail inbox."""
    gmail = await _get_client(user_id, db)
    if not gmail:
        return {"error": "Gmail not connected. Please connect your Google account in Settings."}

    try:
        emails = await gmail.get_recent_emails(days=days, max_results=max_results)
        return {
            "count": len(emails),
            "emails": [
                {
                    "id": e.get("id", ""),
                    "from": e.get("from", "Unknown"),
                    "subject": e.get("subject", "(no subject)"),
                    "date": e.get("date", ""),
                    "preview": (e.get("preview", "") or "")[:200],
                    "is_read": e.get("is_read", True),
                }
                for e in emails
            ],
        }
    except Exception as exc:
        logger.error("MCP read_inbox failed: %s", exc)
        return {"error": f"Failed to read inbox: {str(exc)}"}


# ═══════════════════════════════════════════════════════════
# TOOL: search_emails
# ═══════════════════════════════════════════════════════════

async def search_emails(
    user_id: str,
    db: Session,
    query: str,
    max_results: int = 10,
) -> dict:
    """Search Gmail for emails matching a query."""
    gmail = await _get_client(user_id, db)
    if not gmail:
        return {"error": "Gmail not connected. Please connect your Google account in Settings."}

    try:
        emails = await gmail.search_emails(query=query, max_results=max_results)
        return {
            "query": query,
            "count": len(emails),
            "emails": [
                {
                    "id": e.get("id", ""),
                    "from": e.get("from", "Unknown"),
                    "subject": e.get("subject", "(no subject)"),
                    "date": e.get("date", ""),
                    "preview": (e.get("preview", "") or "")[:200],
                }
                for e in emails
            ],
        }
    except Exception as exc:
        logger.error("MCP search_emails failed: %s", exc)
        return {"error": f"Failed to search emails: {str(exc)}"}


# ═══════════════════════════════════════════════════════════
# TOOL: send_email
# ═══════════════════════════════════════════════════════════

async def send_email(
    user_id: str,
    db: Session,
    to: str,
    subject: str,
    body: str,
) -> dict:
    """Send an email via the user's connected Gmail account."""
    gmail = await _get_client(user_id, db)
    if not gmail:
        return {"error": "Gmail not connected. Please connect your Google account in Settings."}

    try:
        # GmailClient.send_email expects lists for 'to'
        recipients = [addr.strip() for addr in to.split(",")]
        result = await gmail.send_email(to=recipients, subject=subject, body=body)
        return {
            "message": f"Email sent successfully to {to}",
            "message_id": result.get("id", ""),
        }
    except Exception as exc:
        logger.error("MCP send_email failed: %s", exc)
        return {"error": f"Failed to send email: {str(exc)}"}


# ═══════════════════════════════════════════════════════════
# TOOL: send_proposal_email
# ═══════════════════════════════════════════════════════════

async def send_proposal_email(
    user_id: str,
    db: Session,
    proposal_id: str,
    recipient_email: str,
    message: str,
) -> dict:
    """Email a proposal to a recipient with a custom cover message.

    Composes a professional email with the cover message and the full
    proposal content below.
    """
    from app.models.proposal import Proposal

    gmail = await _get_client(user_id, db)
    if not gmail:
        return {"error": "Gmail not connected. Please connect your Google account in Settings."}

    proposal = db.query(Proposal).filter(Proposal.id == proposal_id).first()
    if not proposal:
        return {"error": f"Proposal {proposal_id} not found"}

    # Build email
    subject = f"Proposal: {proposal.title}"
    body = (
        f"{message}\n\n"
        f"{'─' * 50}\n\n"
        f"{proposal.content}\n\n"
        f"{'─' * 50}\n"
        f"Sent via DealMind by ESSHVA\n"
    )

    try:
        recipients = [addr.strip() for addr in recipient_email.split(",")]
        result = await gmail.send_email(to=recipients, subject=subject, body=body)
        logger.info(
            "MCP send_proposal_email: proposal %s → %s",
            proposal_id[:8], recipient_email,
        )
        return {
            "message": f"Proposal '{proposal.title}' sent to {recipient_email}",
            "message_id": result.get("id", ""),
        }
    except Exception as exc:
        logger.error("MCP send_proposal_email failed: %s", exc)
        return {"error": f"Failed to send proposal email: {str(exc)}"}
