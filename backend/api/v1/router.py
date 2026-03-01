"""
Main API v1 router — aggregates all sub-routers.
"""

from fastapi import APIRouter

from api.v1.routes.sessions import router as sessions_router
from api.v1.routes.papers import router as papers_router
from api.v1.routes.chat import router as chat_router
from api.v1.routes.comparison import router as comparison_router
from api.v1.routes.export import router as export_router
from api.v1.routes.analysis import router as analysis_router
from api.v1.routes.verification import router as verification_router
from api.v1.routes.websocket import router as ws_router
from api.v1.routes.health import router as health_router

api_v1_router = APIRouter()

api_v1_router.include_router(sessions_router, prefix="/sessions", tags=["Sessions"])
api_v1_router.include_router(papers_router, prefix="/sessions/{session_id}/papers", tags=["Papers"])
api_v1_router.include_router(chat_router, prefix="/sessions/{session_id}/chat", tags=["Chat"])
api_v1_router.include_router(comparison_router, prefix="/sessions/{session_id}/compare", tags=["Comparison"])
api_v1_router.include_router(export_router, prefix="/sessions/{session_id}/export", tags=["Export"])
api_v1_router.include_router(analysis_router, prefix="/sessions/{session_id}/analysis", tags=["Analysis"])
api_v1_router.include_router(verification_router, prefix="/verify", tags=["Verification"])
api_v1_router.include_router(ws_router, prefix="/ws", tags=["WebSocket"])
api_v1_router.include_router(health_router, prefix="/health", tags=["Health"])
