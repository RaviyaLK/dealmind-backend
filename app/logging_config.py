"""
Centralized logging configuration for DealMind.
Provides coloured, structured logs to the terminal.

Usage in any module:
    import logging
    logger = logging.getLogger(__name__)
"""

import logging
import sys
from datetime import datetime


# ── ANSI colours for terminal ──────────────────────────────────────────
class Colours:
    RESET   = "\033[0m"
    BOLD    = "\033[1m"
    DIM     = "\033[2m"
    # Levels
    DEBUG   = "\033[36m"     # cyan
    INFO    = "\033[32m"     # green
    WARNING = "\033[33m"     # yellow
    ERROR   = "\033[31m"     # red
    CRITICAL = "\033[41m"    # red bg
    # Categories
    LLM     = "\033[35m"     # magenta
    DB      = "\033[34m"     # blue
    RAG     = "\033[96m"     # bright cyan
    AGENT   = "\033[95m"     # bright magenta
    HTTP    = "\033[37m"     # white


LEVEL_COLOURS = {
    "DEBUG":    Colours.DEBUG,
    "INFO":     Colours.INFO,
    "WARNING":  Colours.WARNING,
    "ERROR":    Colours.ERROR,
    "CRITICAL": Colours.CRITICAL,
}

# Map logger names to short tags + colours
CATEGORY_MAP = {
    "app.services.llm":          ("LLM",       Colours.LLM),
    "app.database":              ("DB",        Colours.DB),
    "app.rag":                   ("RAG",       Colours.RAG),
    "app.rag.retriever":         ("RAG",       Colours.RAG),
    "app.rag.vectorstore":       ("VECTOR",    Colours.RAG),
    "app.rag.embeddings":        ("EMBED",     Colours.RAG),
    "app.agents.orchestrator":   ("ORCH",      Colours.AGENT),
    "app.agents.qualification":  ("QUAL",      Colours.AGENT),
    "app.agents.proposal":       ("PROPOSAL",  Colours.AGENT),
    "app.agents.monitoring":     ("MONITOR",   Colours.AGENT),
    "app.routers.documents":     ("DOCS",      Colours.INFO),
    "app.routers.integrations":  ("GMAIL",     Colours.INFO),
    "app.routers.agents":        ("AGENTS",    Colours.AGENT),
    "main":                      ("SERVER",    Colours.BOLD),
}


class DealMindFormatter(logging.Formatter):
    """Custom formatter: coloured level + category tag + message."""

    def format(self, record: logging.LogRecord) -> str:
        ts = datetime.fromtimestamp(record.created).strftime("%H:%M:%S.%f")[:-3]

        level_colour = LEVEL_COLOURS.get(record.levelname, Colours.RESET)
        level_tag = f"{level_colour}{record.levelname:<7}{Colours.RESET}"

        # Resolve category tag
        cat_tag = ""
        cat_colour = Colours.DIM
        for prefix, (tag, colour) in CATEGORY_MAP.items():
            if record.name.startswith(prefix):
                cat_tag = tag
                cat_colour = colour
                break
        if not cat_tag:
            # Fallback: last part of logger name
            cat_tag = record.name.rsplit(".", 1)[-1].upper()[:10]

        category = f"{cat_colour}[{cat_tag}]{Colours.RESET}"

        msg = record.getMessage()

        # Include exception info if present
        exc = ""
        if record.exc_info and record.exc_info[0]:
            exc = f"\n{self.formatException(record.exc_info)}"

        return f"{Colours.DIM}{ts}{Colours.RESET} {level_tag} {category} {msg}{exc}"


def setup_logging(level: str = "DEBUG"):
    """Configure root logger with DealMind formatter.

    Call once at application startup (in main.py lifespan).
    """
    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.DEBUG))

    # Remove any existing handlers
    for h in root.handlers[:]:
        root.removeHandler(h)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(DealMindFormatter())
    root.addHandler(handler)

    # Quiet down noisy third-party loggers
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.error").setLevel(logging.INFO)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("chromadb").setLevel(logging.WARNING)
    logging.getLogger("sentence_transformers").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)

    logger = logging.getLogger("main")
    logger.info("Logging initialised (level=%s)", level)
