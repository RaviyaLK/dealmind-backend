"""MCP Proposal Tools — Read, edit, and manage proposal sections.

Each tool operates on the proposal's markdown content stored in the DB.
Tools receive `proposal_id` and `db` (SQLAlchemy Session) via context
injection from the MCPToolRegistry.
"""

import re
import logging
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════
# HELPER: Parse markdown into sections
# ═══════════════════════════════════════════════════════════

def _parse_sections(content: str) -> List[Dict[str, Any]]:
    """Parse markdown content into a list of sections.

    Each section is:
        {
            "title": "Executive Summary",
            "level": 2,            # number of '#' chars
            "heading_line": "## Executive Summary",
            "start": 5,            # line index of heading
            "end": 18,             # line index of next heading (or len(lines))
        }
    """
    lines = content.split("\n")
    sections: List[Dict[str, Any]] = []

    for i, line in enumerate(lines):
        stripped = line.strip()
        match = re.match(r"^(#{1,3})\s+(.+)$", stripped)
        if match:
            level = len(match.group(1))
            title = match.group(2).strip()
            # Strip bold markers like **Executive Summary**
            if title.startswith("**") and title.endswith("**"):
                title = title[2:-2].strip()
            sections.append({
                "title": title,
                "level": level,
                "heading_line": stripped,
                "start": i,
                "end": len(lines),  # will be updated below
            })

    # Set end boundaries: each section ends where the next section of same
    # or higher level begins
    for idx in range(len(sections)):
        current_level = sections[idx]["level"]
        for j in range(idx + 1, len(sections)):
            if sections[j]["level"] <= current_level:
                sections[idx]["end"] = sections[j]["start"]
                break

    return sections


def _find_section(sections: List[dict], name: str) -> Optional[dict]:
    """Find a section by title (case-insensitive, partial match)."""
    name_lower = name.lower().strip()
    # Try exact match first
    for s in sections:
        if s["title"].lower().strip() == name_lower:
            return s
    # Try "contains" match
    for s in sections:
        if name_lower in s["title"].lower():
            return s
    return None


def _get_proposal(proposal_id: str, db: Session):
    """Load proposal from DB (returns model or None)."""
    from app.models.proposal import Proposal
    return db.query(Proposal).filter(Proposal.id == proposal_id).first()


# ═══════════════════════════════════════════════════════════
# TOOL: list_sections
# ═══════════════════════════════════════════════════════════

def list_sections(proposal_id: str, db: Session) -> dict:
    """List all section titles in the proposal."""
    proposal = _get_proposal(proposal_id, db)
    if not proposal:
        return {"error": f"Proposal {proposal_id} not found"}

    sections = _parse_sections(proposal.content or "")
    titles = [
        {"title": s["title"], "level": s["level"]}
        for s in sections
    ]
    return {"sections": titles, "count": len(titles)}


# ═══════════════════════════════════════════════════════════
# TOOL: get_proposal
# ═══════════════════════════════════════════════════════════

def get_proposal(proposal_id: str, db: Session) -> dict:
    """Get the full proposal content and metadata."""
    proposal = _get_proposal(proposal_id, db)
    if not proposal:
        return {"error": f"Proposal {proposal_id} not found"}

    return {
        "id": proposal.id,
        "title": proposal.title,
        "status": proposal.status,
        "version": proposal.version,
        "content": proposal.content,
    }


# ═══════════════════════════════════════════════════════════
# TOOL: update_section
# ═══════════════════════════════════════════════════════════

def update_section(
    proposal_id: str,
    section_name: str,
    new_content: str,
    db: Session,
) -> dict:
    """Update a specific section of the proposal by replacing its body content.

    Keeps the original heading line and replaces everything between it and the
    next heading of same/higher level.
    """
    proposal = _get_proposal(proposal_id, db)
    if not proposal:
        return {"error": f"Proposal {proposal_id} not found"}

    sections = _parse_sections(proposal.content or "")
    target = _find_section(sections, section_name)
    if not target:
        available = [s["title"] for s in sections]
        return {"error": f"Section '{section_name}' not found. Available: {available}"}

    lines = (proposal.content or "").split("\n")

    # Keep the heading line, replace body content
    heading_line = lines[target["start"]]
    before = lines[: target["start"]]
    after = lines[target["end"]:]

    # Build new section: heading + blank line + new content + blank line
    new_section_lines = [heading_line, ""] + new_content.strip().split("\n") + [""]

    updated_lines = before + new_section_lines + after
    proposal.content = "\n".join(updated_lines)
    db.commit()

    logger.info("MCP update_section: '%s' in proposal %s", section_name, proposal_id[:8])
    return {
        "message": f"Section '{target['title']}' updated successfully",
        "section_title": target["title"],
    }


# ═══════════════════════════════════════════════════════════
# TOOL: add_section
# ═══════════════════════════════════════════════════════════

def add_section(
    proposal_id: str,
    section_name: str,
    content: str,
    db: Session,
    after_section: str = "",
) -> dict:
    """Add a new section to the proposal.

    If `after_section` is provided, inserts after that section.
    Otherwise appends at the end.
    """
    proposal = _get_proposal(proposal_id, db)
    if not proposal:
        return {"error": f"Proposal {proposal_id} not found"}

    lines = (proposal.content or "").split("\n")

    # Determine heading level (default ## for new sections)
    new_heading = f"## {section_name}"
    new_section_lines = ["", new_heading, ""] + content.strip().split("\n") + [""]

    if after_section:
        sections = _parse_sections(proposal.content or "")
        anchor = _find_section(sections, after_section)
        if not anchor:
            return {"error": f"Anchor section '{after_section}' not found"}

        # Insert after the anchor section's end
        insert_at = anchor["end"]
        updated_lines = lines[:insert_at] + new_section_lines + lines[insert_at:]
    else:
        # Append at end
        updated_lines = lines + new_section_lines

    proposal.content = "\n".join(updated_lines)
    db.commit()

    logger.info("MCP add_section: '%s' to proposal %s", section_name, proposal_id[:8])
    return {
        "message": f"Section '{section_name}' added successfully",
        "position": f"after '{after_section}'" if after_section else "end of proposal",
    }


# ═══════════════════════════════════════════════════════════
# TOOL: remove_section
# ═══════════════════════════════════════════════════════════

def remove_section(
    proposal_id: str,
    section_name: str,
    db: Session,
) -> dict:
    """Remove an entire section (heading + body) from the proposal."""
    proposal = _get_proposal(proposal_id, db)
    if not proposal:
        return {"error": f"Proposal {proposal_id} not found"}

    sections = _parse_sections(proposal.content or "")
    target = _find_section(sections, section_name)
    if not target:
        available = [s["title"] for s in sections]
        return {"error": f"Section '{section_name}' not found. Available: {available}"}

    lines = (proposal.content or "").split("\n")

    # Remove lines from section start to section end
    before = lines[: target["start"]]
    after = lines[target["end"]:]

    # Clean up extra blank lines at the join
    while before and before[-1].strip() == "" and after and after[0].strip() == "":
        before.pop()

    proposal.content = "\n".join(before + after)
    db.commit()

    logger.info("MCP remove_section: '%s' from proposal %s", section_name, proposal_id[:8])
    return {
        "message": f"Section '{target['title']}' removed successfully",
    }
