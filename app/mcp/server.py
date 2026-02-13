"""Standalone MCP Server for DealMind.

This file exposes DealMind's proposal and Gmail tools as a proper MCP server
using the FastMCP SDK. External MCP clients (Claude Desktop, other AI agents,
etc.) can connect to this server to use DealMind's tools.

Usage:
    # Run as a standalone MCP server (stdio transport)
    python -m app.mcp.server

    # Or import and run programmatically
    from app.mcp.server import mcp
    mcp.run()
"""

import os
import sys
import re
import json
import logging

# Ensure the project root is on the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

try:
    from mcp.server.fastmcp import FastMCP
except ImportError:
    # Graceful fallback if mcp package not installed
    class _Stub:
        def __init__(self, *a, **kw): pass
        def tool(self, *a, **kw):
            def decorator(f): return f
            return decorator
        def run(self): print("MCP SDK not installed. Run: pip install mcp")
    FastMCP = _Stub

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════
# MCP Server Instance
# ═══════════════════════════════════════════════════════════

mcp = FastMCP(
    "DealMind",
    version="1.0.0",
)


# ═══════════════════════════════════════════════════════════
# Proposal Tools
# ═══════════════════════════════════════════════════════════

@mcp.tool()
def list_proposal_sections(proposal_id: str) -> str:
    """List all section titles in a DealMind proposal.

    Args:
        proposal_id: The UUID of the proposal
    """
    from app.database import SessionLocal
    from app.mcp.tools.proposal_tools import list_sections

    db = SessionLocal()
    try:
        result = list_sections(proposal_id=proposal_id, db=db)
        return json.dumps(result, indent=2)
    finally:
        db.close()


@mcp.tool()
def get_proposal(proposal_id: str) -> str:
    """Get the full content and metadata of a DealMind proposal.

    Args:
        proposal_id: The UUID of the proposal
    """
    from app.database import SessionLocal
    from app.mcp.tools.proposal_tools import get_proposal as _get

    db = SessionLocal()
    try:
        result = _get(proposal_id=proposal_id, db=db)
        return json.dumps(result, indent=2)
    finally:
        db.close()


@mcp.tool()
def update_proposal_section(
    proposal_id: str,
    section_name: str,
    new_content: str,
) -> str:
    """Update a specific section of a DealMind proposal.

    Args:
        proposal_id: The UUID of the proposal
        section_name: The heading text of the section (e.g., "Executive Summary")
        new_content: New markdown content for the section body (no heading)
    """
    from app.database import SessionLocal
    from app.mcp.tools.proposal_tools import update_section

    db = SessionLocal()
    try:
        result = update_section(
            proposal_id=proposal_id,
            section_name=section_name,
            new_content=new_content,
            db=db,
        )
        return json.dumps(result, indent=2)
    finally:
        db.close()


@mcp.tool()
def add_proposal_section(
    proposal_id: str,
    section_name: str,
    content: str,
    after_section: str = "",
) -> str:
    """Add a new section to a DealMind proposal.

    Args:
        proposal_id: The UUID of the proposal
        section_name: Title for the new section
        content: Markdown content for the section
        after_section: Insert after this section. If empty, appends at end.
    """
    from app.database import SessionLocal
    from app.mcp.tools.proposal_tools import add_section

    db = SessionLocal()
    try:
        result = add_section(
            proposal_id=proposal_id,
            section_name=section_name,
            content=content,
            after_section=after_section,
            db=db,
        )
        return json.dumps(result, indent=2)
    finally:
        db.close()


@mcp.tool()
def remove_proposal_section(
    proposal_id: str,
    section_name: str,
) -> str:
    """Remove an entire section from a DealMind proposal.

    Args:
        proposal_id: The UUID of the proposal
        section_name: Heading text of the section to remove
    """
    from app.database import SessionLocal
    from app.mcp.tools.proposal_tools import remove_section

    db = SessionLocal()
    try:
        result = remove_section(
            proposal_id=proposal_id,
            section_name=section_name,
            db=db,
        )
        return json.dumps(result, indent=2)
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════
# Gmail Tools
# ═══════════════════════════════════════════════════════════

@mcp.tool()
async def gmail_send_proposal(
    proposal_id: str,
    recipient_email: str,
    message: str,
    user_id: str = "demo",
) -> str:
    """Send a DealMind proposal via Gmail to a recipient.

    Args:
        proposal_id: The UUID of the proposal to send
        recipient_email: Email address of the recipient
        message: Cover message to include above the proposal content
        user_id: The DealMind user ID (defaults to demo user)
    """
    from app.database import SessionLocal
    from app.mcp.tools.gmail_tools import send_proposal_email

    db = SessionLocal()
    try:
        result = await send_proposal_email(
            user_id=user_id,
            db=db,
            proposal_id=proposal_id,
            recipient_email=recipient_email,
            message=message,
        )
        return json.dumps(result, indent=2)
    finally:
        db.close()


@mcp.tool()
async def gmail_read_inbox(
    days: int = 7,
    max_results: int = 10,
    user_id: str = "demo",
) -> str:
    """Read recent emails from the user's Gmail inbox.

    Args:
        days: Number of days to look back (default 7)
        max_results: Maximum number of emails to return (default 10)
        user_id: The DealMind user ID (defaults to demo user)
    """
    from app.database import SessionLocal
    from app.mcp.tools.gmail_tools import read_inbox

    db = SessionLocal()
    try:
        result = await read_inbox(user_id=user_id, db=db, days=days, max_results=max_results)
        return json.dumps(result, indent=2)
    finally:
        db.close()


@mcp.tool()
async def gmail_search(
    query: str,
    max_results: int = 10,
    user_id: str = "demo",
) -> str:
    """Search Gmail for emails matching a query.

    Args:
        query: Gmail search query (e.g., "from:john subject:proposal")
        max_results: Maximum number of emails to return (default 10)
        user_id: The DealMind user ID (defaults to demo user)
    """
    from app.database import SessionLocal
    from app.mcp.tools.gmail_tools import search_emails

    db = SessionLocal()
    try:
        result = await search_emails(user_id=user_id, db=db, query=query, max_results=max_results)
        return json.dumps(result, indent=2)
    finally:
        db.close()


@mcp.tool()
async def gmail_send(
    to: str,
    subject: str,
    body: str,
    user_id: str = "demo",
) -> str:
    """Send an email via the user's connected Gmail account.

    Args:
        to: Recipient email address (comma-separated for multiple)
        subject: Email subject line
        body: Email body text
        user_id: The DealMind user ID (defaults to demo user)
    """
    from app.database import SessionLocal
    from app.mcp.tools.gmail_tools import send_email

    db = SessionLocal()
    try:
        result = await send_email(user_id=user_id, db=db, to=to, subject=subject, body=body)
        return json.dumps(result, indent=2)
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════
# WhatsApp Tools
# ═══════════════════════════════════════════════════════════

@mcp.tool()
def whatsapp_send_alert(
    message: str,
    to_number: str = "",
) -> str:
    """Send a WhatsApp message to the admin (e.g., for deal risk alerts).

    Args:
        message: The alert message to send via WhatsApp
        to_number: Recipient WhatsApp number in E.164 format (optional, defaults to admin)
    """
    from app.mcp.tools.whatsapp_tools import send_whatsapp_alert

    result = send_whatsapp_alert(
        message=message,
        to_number=to_number if to_number else None,
    )
    return json.dumps(result, indent=2)


@mcp.tool()
def whatsapp_deal_risk_alert(
    deal_title: str,
    client_name: str,
    alert_type: str,
    severity: str,
    health_score: int,
    sentiment_score: float,
    description: str,
    to_number: str = "",
) -> str:
    """Send a formatted deal risk alert via WhatsApp with full deal details.

    Args:
        deal_title: Name/title of the deal
        client_name: Client company or contact name
        alert_type: Type of alert (sentiment_drop, deadline_risk, competitor_mention)
        severity: Alert severity (critical, high, medium)
        health_score: Current deal health score (0-100)
        sentiment_score: Overall sentiment score (-1.0 to 1.0)
        description: Alert description from the monitoring agent
        to_number: Override recipient number (optional, defaults to admin)
    """
    from app.mcp.tools.whatsapp_tools import send_deal_risk_alert

    result = send_deal_risk_alert(
        deal_title=deal_title,
        client_name=client_name,
        alert_type=alert_type,
        severity=severity,
        health_score=health_score,
        sentiment_score=sentiment_score,
        description=description,
        to_number=to_number if to_number else None,
    )
    return json.dumps(result, indent=2)


# ═══════════════════════════════════════════════════════════
# Run as standalone server
# ═══════════════════════════════════════════════════════════

if __name__ == "__main__":
    mcp.run()
