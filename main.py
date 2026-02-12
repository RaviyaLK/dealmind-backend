"""
DealMind Backend API
====================
AI-powered deal intelligence platform.
Agent: Quinn | Orchestrator: LangGraph | LLM: DeepSeek (OpenRouter)

Built for Agentic AI Hackathon 2026 by Hallucination Squad.
"""

import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from app.config import settings
from app.logging_config import setup_logging
from app.database import engine, init_db
from app.admin import setup_admin

# Import routers
from app.routers.auth import router as auth_router
from app.routers.deals import router as deals_router
from app.routers.employees import router as employees_router
from app.routers.documents import router as documents_router
from app.routers.alerts import router as alerts_router
from app.routers.proposals import router as proposals_router
from app.routers.agents import router as agents_router
from app.routers.rag import router as rag_router
from app.routers.assignments import router as assignments_router
from app.routers.integrations import router as integrations_router
from app.routers.websocket import router as ws_router

logger = logging.getLogger("main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    # ── Startup ──
    setup_logging("DEBUG" if settings.DEBUG else "INFO")
    logger.info("Starting DealMind Backend v1.0.0")
    logger.info("LLM model: %s", settings.LLM_MODEL)

    init_db()
    logger.info("Database tables initialised (%s)", settings.DATABASE_URL.split("://")[0])

    Path(settings.UPLOAD_DIR).mkdir(parents=True, exist_ok=True)
    Path(settings.CHROMA_PERSIST_DIR).mkdir(parents=True, exist_ok=True)
    logger.info("Upload dir: %s | ChromaDB dir: %s", settings.UPLOAD_DIR, settings.CHROMA_PERSIST_DIR)
    logger.info("DealMind Backend ready — listening on %s:%s", settings.HOST, settings.PORT)

    yield

    # ── Shutdown ──
    logger.info("Shutting down DealMind Backend...")


app = FastAPI(
    title="DealMind API",
    description="AI-powered deal intelligence platform. Converts unstructured sales data into strategic actions.",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Admin UI (like Prisma Studio) — available at /admin
setup_admin(app, engine)

# Register routers
app.include_router(auth_router)
app.include_router(deals_router)
app.include_router(employees_router)
app.include_router(assignments_router)
app.include_router(documents_router)
app.include_router(alerts_router)
app.include_router(proposals_router)
app.include_router(agents_router)
app.include_router(rag_router)
app.include_router(integrations_router)
app.include_router(ws_router)

# Serve uploaded files statically (for development)
uploads_path = Path(settings.UPLOAD_DIR)
if uploads_path.exists():
    app.mount("/files", StaticFiles(directory=str(uploads_path)), name="files")


@app.get("/", tags=["Health"])
async def root():
    return {
        "service": "DealMind API",
        "version": "1.0.0",
        "agent": "Quinn",
        "status": "operational",
    }


@app.get("/health", tags=["Health"])
async def health_check():
    return {
        "status": "healthy",
        "database": "connected",
        "agent": "quinn",
        "flows": ["qualification", "proposal", "monitoring"],
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
    )
