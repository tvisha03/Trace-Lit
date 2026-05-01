from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from shared.errors import TraceLitError, AllProvidersFailedError
from shared.logger import get_logger

logger = get_logger(__name__)

def register_exception_handlers(app: FastAPI) -> None:

    @app.exception_handler(AllProvidersFailedError)
    async def all_providers_failed_handler(
        _request: Request, exc: AllProvidersFailedError
    ) -> JSONResponse:
        logger.error(f"All LLM providers failed: {exc.message}")
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.message},
            headers={"Retry-After": "60"},
        )

    @app.exception_handler(TraceLitError)
    async def tracelit_error_handler(_request: Request, exc: TraceLitError) -> JSONResponse:
        logger.warning(f"[{exc.status_code}] {exc.message}")
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.message},
        )

    @app.exception_handler(Exception)
    async def generic_error_handler(_request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled exception")
        return JSONResponse(
            status_code=500,
            content={"detail": "An unexpected error occurred. Please try again."},
        )

