from app.routers.deals import router as deals_router
from app.routers.employees import router as employees_router
from app.routers.documents import router as documents_router
from app.routers.alerts import router as alerts_router
from app.routers.proposals import router as proposals_router
from app.routers.agents import router as agents_router
from app.routers.rag import router as rag_router

__all__ = [
    "deals_router",
    "employees_router",
    "documents_router",
    "alerts_router",
    "proposals_router",
    "agents_router",
    "rag_router",
]
