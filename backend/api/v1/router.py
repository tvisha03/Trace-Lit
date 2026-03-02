"""TraceLit — API v1 Top-Level Router."""

from fastapi import APIRouter

from api.v1.papers.router import router as papers_router
from api.v1.sessions.router import router as sessions_router
from api.v1.chat.router import router as chat_router
from api.v1.comparison.router import router as comparison_router
from api.v1.export.router import router as export_router
from api.v1.analysis.router import router as analysis_router
from api.v1.settings.router import router as settings_router

router = APIRouter()

router.include_router(papers_router, tags=["papers"])
router.include_router(sessions_router, tags=["sessions"])
router.include_router(chat_router, tags=["chat"])
router.include_router(comparison_router, tags=["comparison"])
router.include_router(export_router, tags=["export"])
router.include_router(analysis_router, tags=["analysis"])
router.include_router(settings_router, tags=["settings"])
