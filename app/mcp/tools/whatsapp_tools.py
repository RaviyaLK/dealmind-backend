"""WhatsApp MCP Tools — Send WhatsApp alerts via Twilio.

Provides tools for sending real-time WhatsApp notifications when the
monitoring agent detects deal risks (sentiment drops, health score
critical, competitor mentions).

Setup:
    1. Create a Twilio account at https://www.twilio.com
    2. Enable the WhatsApp Sandbox in Twilio Console → Messaging → Try It Out → WhatsApp
    3. Join the sandbox by sending the provided code from your WhatsApp to the Twilio number
    4. Set env vars: TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN,
       TWILIO_WHATSAPP_FROM, ADMIN_WHATSAPP_NUMBER
"""

import logging
from typing import Optional

from app.config import settings

logger = logging.getLogger(__name__)


def _get_twilio_client():
    """Create a Twilio client using configured credentials.

    Returns None if Twilio is not configured (missing credentials).
    """
    if not settings.TWILIO_ACCOUNT_SID or not settings.TWILIO_AUTH_TOKEN:
        logger.warning("Twilio credentials not configured — WhatsApp alerts disabled")
        return None

    try:
        from twilio.rest import Client
        return Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
    except ImportError:
        logger.error("twilio package not installed. Run: pip install twilio")
        return None
    except Exception as e:
        logger.error(f"Failed to create Twilio client: {e}")
        return None


def send_whatsapp_alert(
    message: str,
    to_number: Optional[str] = None,
) -> dict:
    """Send a WhatsApp message to the admin when a deal risk is detected.

    Args:
        message: The alert message to send (plain text, supports basic formatting).
        to_number: Override recipient WhatsApp number (E.164 format, e.g. +94771234567).
                   If not provided, uses ADMIN_WHATSAPP_NUMBER from config.

    Returns:
        dict with status and message SID or error details.
    """
    recipient = to_number or settings.ADMIN_WHATSAPP_NUMBER
    if not recipient:
        return {
            "status": "error",
            "error": "No recipient WhatsApp number configured. Set ADMIN_WHATSAPP_NUMBER in .env",
        }

    client = _get_twilio_client()
    if client is None:
        return {
            "status": "error",
            "error": "Twilio not configured. Set TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN in .env",
        }

    from_number = settings.TWILIO_WHATSAPP_FROM
    if not from_number:
        return {
            "status": "error",
            "error": "TWILIO_WHATSAPP_FROM not configured in .env",
        }

    # Ensure WhatsApp prefix
    if not from_number.startswith("whatsapp:"):
        from_number = f"whatsapp:{from_number}"
    if not recipient.startswith("whatsapp:"):
        recipient = f"whatsapp:{recipient}"

    try:
        msg = client.messages.create(
            body=message,
            from_=from_number,
            to=recipient,
        )
        logger.info(f"WhatsApp alert sent — SID: {msg.sid}, to: {recipient}")
        return {
            "status": "ok",
            "message_sid": msg.sid,
            "to": recipient,
            "message": "WhatsApp alert sent successfully",
        }
    except Exception as e:
        logger.error(f"Failed to send WhatsApp alert: {e}")
        return {
            "status": "error",
            "error": str(e),
        }


def send_deal_risk_alert(
    deal_title: str,
    client_name: str,
    alert_type: str,
    severity: str,
    health_score: int,
    sentiment_score: float,
    description: str,
    to_number: Optional[str] = None,
) -> dict:
    """Send a formatted deal risk alert to admin via WhatsApp.

    This is a higher-level wrapper that formats a nice alert message
    from the monitoring agent's output.

    Args:
        deal_title: Name/title of the deal.
        client_name: Client company or contact name.
        alert_type: Type of alert (sentiment_drop, deadline_risk, competitor_mention).
        severity: Alert severity (critical, high, medium).
        health_score: Current deal health score (0-100).
        sentiment_score: Overall sentiment (-1.0 to 1.0).
        description: Alert description from the monitoring agent.
        to_number: Override recipient number (defaults to ADMIN_WHATSAPP_NUMBER).

    Returns:
        dict with status and message details.
    """
    # Build severity emoji and label
    severity_map = {
        "critical": "🚨 CRITICAL",
        "high": "⚠️ HIGH",
        "medium": "📋 MEDIUM",
        "info": "ℹ️ INFO",
    }
    severity_label = severity_map.get(severity, f"🔔 {severity.upper()}")

    # Build alert type label
    type_map = {
        "sentiment_drop": "Negative Sentiment",
        "deadline_risk": "Health Score Critical",
        "competitor_mention": "Competitor Mentioned",
        "positive_update": "Positive Update",
    }
    type_label = type_map.get(alert_type, alert_type)

    # Format the WhatsApp message
    message = (
        f"{severity_label}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"*DealMind Alert*\n\n"
        f"*Deal:* {deal_title}\n"
        f"*Client:* {client_name}\n"
        f"*Type:* {type_label}\n"
        f"*Health Score:* {health_score}%\n"
        f"*Sentiment:* {sentiment_score:.2f}\n\n"
        f"*Details:*\n{description}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"_Open DealMind dashboard to review and take action._"
    )

    return send_whatsapp_alert(message=message, to_number=to_number)
