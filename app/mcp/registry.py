"""MCP Tool Registry — discovers, stores, and executes MCP-compatible tools.

The registry provides:
  - Tool registration with MCP-compatible JSON schemas
  - Tool discovery (list tools for LLM prompts)
  - Tool execution with context injection (user_id, db, proposal_id)
"""

import inspect
import json
import logging
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class MCPToolRegistry:
    """Registry for MCP-compatible tools with context injection."""

    def __init__(self, name: str = "default"):
        self.name = name
        self._tools: Dict[str, Callable] = {}
        self._schemas: Dict[str, dict] = {}

    # ── Registration ──

    def register(
        self,
        name: str,
        func: Callable,
        description: str,
        input_schema: dict,
    ):
        """Register a tool with an MCP-compatible schema.

        Args:
            name: Unique tool name (e.g., "update_section")
            func: Callable that implements the tool (sync or async)
            description: Human-readable description for the LLM
            input_schema: JSON Schema for the tool's input parameters
        """
        self._tools[name] = func
        self._schemas[name] = {
            "name": name,
            "description": description,
            "inputSchema": {
                "type": "object",
                **input_schema,
            },
        }
        logger.info("MCP tool registered: %s", name)

    # ── Discovery ──

    def list_tools(self) -> List[dict]:
        """Return all tool schemas in MCP-compatible format."""
        return list(self._schemas.values())

    def get_tools_for_prompt(self) -> str:
        """Format tool descriptions for inclusion in an LLM prompt."""
        lines = []
        for schema in self._schemas.values():
            name = schema["name"]
            desc = schema["description"]
            props = schema["inputSchema"].get("properties", {})

            # Build a concise input description
            params = []
            for pname, pdef in props.items():
                ptype = pdef.get("type", "string")
                pdesc = pdef.get("description", "")
                params.append(f'    "{pname}": {ptype} — {pdesc}' if pdesc else f'    "{pname}": {ptype}')

            param_block = "\n".join(params) if params else "    (no parameters)"
            lines.append(f"- **{name}**: {desc}\n  Input:\n{param_block}")

        return "\n".join(lines)

    # ── Execution ──

    async def execute(
        self,
        name: str,
        arguments: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> dict:
        """Execute a tool by name, injecting context into arguments.

        Context keys (user_id, db, proposal_id, etc.) are merged into the
        function's keyword arguments — but ONLY if the function signature
        actually accepts them.  This lets tools remain clean (they declare
        only the params they need).

        Returns:
            {"status": "ok", "result": <tool output>}
            {"status": "error", "error": "<message>"}
        """
        if name not in self._tools:
            return {"status": "error", "error": f"Unknown tool: {name}"}

        func = self._tools[name]
        merged = {**arguments}

        # Inject context values ONLY for params the function accepts
        if context:
            sig = inspect.signature(func)
            for key, value in context.items():
                if key in sig.parameters and key not in merged:
                    merged[key] = value

        logger.info("MCP execute: %s(%s)", name, list(merged.keys()))

        try:
            result = func(**merged)
            if inspect.iscoroutine(result):
                result = await result
            return {"status": "ok", "result": result}
        except Exception as exc:
            logger.error("MCP tool %s failed: %s", name, exc)
            return {"status": "error", "error": str(exc)}


# ═══════════════════════════════════════════════════════════
# Global registries — lazily populated on first access
# ═══════════════════════════════════════════════════════════

proposal_registry = MCPToolRegistry("proposal")
full_registry = MCPToolRegistry("full")
_is_setup = False


def _setup():
    """Register all tools into the global registries."""
    from app.mcp.tools import proposal_tools, gmail_tools, whatsapp_tools

    # ── Proposal tools ──
    _proposal_tools = [
        (
            "list_sections",
            proposal_tools.list_sections,
            "List all section titles in the proposal",
            {
                "properties": {
                    "proposal_id": {"type": "string", "description": "The proposal UUID"},
                },
                "required": ["proposal_id"],
            },
        ),
        (
            "get_proposal",
            proposal_tools.get_proposal,
            "Get the full proposal content and metadata",
            {
                "properties": {
                    "proposal_id": {"type": "string", "description": "The proposal UUID"},
                },
                "required": ["proposal_id"],
            },
        ),
        (
            "update_section",
            proposal_tools.update_section,
            "Update a specific section of the proposal by replacing its content",
            {
                "properties": {
                    "proposal_id": {"type": "string", "description": "The proposal UUID"},
                    "section_name": {"type": "string", "description": "Heading text to match (e.g. 'Executive Summary')"},
                    "new_content": {"type": "string", "description": "New markdown content for this section (do NOT include the heading line itself)"},
                },
                "required": ["proposal_id", "section_name", "new_content"],
            },
        ),
        (
            "add_section",
            proposal_tools.add_section,
            "Add a new section to the proposal after a specified section",
            {
                "properties": {
                    "proposal_id": {"type": "string", "description": "The proposal UUID"},
                    "section_name": {"type": "string", "description": "Title for the new section"},
                    "content": {"type": "string", "description": "Markdown content for the new section"},
                    "after_section": {"type": "string", "description": "Insert after this section (heading text). If empty, appends at the end."},
                },
                "required": ["proposal_id", "section_name", "content"],
            },
        ),
        (
            "remove_section",
            proposal_tools.remove_section,
            "Remove an entire section from the proposal",
            {
                "properties": {
                    "proposal_id": {"type": "string", "description": "The proposal UUID"},
                    "section_name": {"type": "string", "description": "Heading text of the section to remove"},
                },
                "required": ["proposal_id", "section_name"],
            },
        ),
    ]

    for name, func, desc, schema in _proposal_tools:
        proposal_registry.register(name, func, desc, schema)
        full_registry.register(name, func, desc, schema)

    # ── Gmail tools ──
    _gmail_tools = [
        (
            "read_inbox",
            gmail_tools.read_inbox,
            "Read recent emails from the user's Gmail inbox",
            {
                "properties": {
                    "days": {"type": "integer", "description": "Number of days to look back (default 7)"},
                    "max_results": {"type": "integer", "description": "Max emails to return (default 10)"},
                },
                "required": [],
            },
        ),
        (
            "search_emails",
            gmail_tools.search_emails,
            "Search Gmail for emails matching a query",
            {
                "properties": {
                    "query": {"type": "string", "description": "Gmail search query (e.g. 'from:john subject:proposal')"},
                    "max_results": {"type": "integer", "description": "Max emails to return (default 10)"},
                },
                "required": ["query"],
            },
        ),
        (
            "send_email",
            gmail_tools.send_email,
            "Send an email via Gmail",
            {
                "properties": {
                    "to": {"type": "string", "description": "Recipient email address"},
                    "subject": {"type": "string", "description": "Email subject line"},
                    "body": {"type": "string", "description": "Email body text"},
                },
                "required": ["to", "subject", "body"],
            },
        ),
        (
            "send_proposal_email",
            gmail_tools.send_proposal_email,
            "Email the current proposal to a recipient with a custom cover message",
            {
                "properties": {
                    "proposal_id": {"type": "string", "description": "The proposal UUID to send"},
                    "recipient_email": {"type": "string", "description": "Recipient email address"},
                    "message": {"type": "string", "description": "Cover message to include above the proposal"},
                },
                "required": ["proposal_id", "recipient_email", "message"],
            },
        ),
    ]

    for name, func, desc, schema in _gmail_tools:
        full_registry.register(name, func, desc, schema)

    # ── WhatsApp tools ──
    _whatsapp_tools = [
        (
            "send_whatsapp_alert",
            whatsapp_tools.send_whatsapp_alert,
            "Send a WhatsApp message to the admin (e.g., deal risk notifications)",
            {
                "properties": {
                    "message": {"type": "string", "description": "The alert message to send via WhatsApp"},
                    "to_number": {"type": "string", "description": "Recipient WhatsApp number in E.164 format (optional, defaults to admin)"},
                },
                "required": ["message"],
            },
        ),
        (
            "send_deal_risk_alert",
            whatsapp_tools.send_deal_risk_alert,
            "Send a formatted deal risk alert to admin via WhatsApp with deal details",
            {
                "properties": {
                    "deal_title": {"type": "string", "description": "Name of the deal"},
                    "client_name": {"type": "string", "description": "Client company or contact name"},
                    "alert_type": {"type": "string", "description": "Type: sentiment_drop, deadline_risk, competitor_mention"},
                    "severity": {"type": "string", "description": "Severity: critical, high, medium"},
                    "health_score": {"type": "integer", "description": "Current deal health (0-100)"},
                    "sentiment_score": {"type": "number", "description": "Overall sentiment (-1.0 to 1.0)"},
                    "description": {"type": "string", "description": "Alert description"},
                },
                "required": ["deal_title", "client_name", "alert_type", "severity",
                             "health_score", "sentiment_score", "description"],
            },
        ),
    ]

    for name, func, desc, schema in _whatsapp_tools:
        full_registry.register(name, func, desc, schema)

    global _is_setup
    _is_setup = True
    logger.info("MCP registry setup complete: %d proposal tools, %d full tools",
                len(proposal_registry._tools), len(full_registry._tools))


def ensure_setup():
    """Ensure tools are registered. Called lazily on first use."""
    if not _is_setup:
        _setup()
