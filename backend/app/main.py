"""
Lumenis AI — FastAPI application entry point.

Assembles the application with middleware, routers, startup events,
and global exception handlers.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.api.routes.health import router as health_router
from app.api.routes.upload import router as upload_router
from app.api.routes.analysis import router as analysis_router
from app.api.routes.chat import router as chat_router

# ── Logging ──────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s │ %(levelname)-8s │ %(name)s │ %(message)s",
)
logger = logging.getLogger(__name__)


# ── Lifespan (startup / shutdown) ────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: run startup tasks then yield to serve."""
    # ── Startup ──────────────────────────────────────────────────────
    logger.info("🚀 Lumenis AI starting up …")

    # Initialise database tables
    try:
        from app.db.session import init_db

        await init_db()
        logger.info("Database tables initialised.")
    except Exception as exc:
        logger.error("Database initialisation failed: %s", exc)

    # Ensure the upload directory exists
    upload_dir = Path(settings.UPLOAD_DIR)
    upload_dir.mkdir(parents=True, exist_ok=True)
    logger.info("Upload directory ready: %s", upload_dir.resolve())

    # Initialize FastAPILimiter
    import redis.asyncio as redis
    from fastapi_limiter import FastAPILimiter
    try:
        redis_conn = redis.from_url(settings.REDIS_URL, encoding="utf8")
        await FastAPILimiter.init(redis_conn)
        logger.info("Rate limiter initialized with Redis.")
    except Exception as exc:
        logger.warning("Could not initialize rate limiter: %s", exc)

    logger.info("✅ Lumenis AI ready to serve requests.")
    yield
    # ── Shutdown ─────────────────────────────────────────────────────
    logger.info("👋 Lumenis AI shutting down …")


# ── Application factory ─────────────────────────────────────────────
app = FastAPI(
    title="Lumenis AI",
    description=(
        "Multimodal medical image analysis system powered by Gemini, "
        "RAG retrieval, and structured report generation."
    ),
    version="0.1.0",
    lifespan=lifespan,
)


# ── CORS middleware ──────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(health_router, prefix="/api")
app.include_router(upload_router, prefix="/api")
app.include_router(analysis_router, prefix="/api")
app.include_router(chat_router, prefix="/api")


# ── Root endpoint ────────────────────────────────────────────────────
@app.get("/", tags=["root"])
async def root() -> dict:
    """Welcome endpoint — confirms the API is running."""
    return {
        "message": "Welcome to Lumenis AI — Multimodal Medical Image Analysis",
        "version": "0.1.0",
        "docs": "/docs",
    }


# ── Global exception handlers ───────────────────────────────────────
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """Uniform JSON shape for all HTTP errors."""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": True,
            "status_code": exc.status_code,
            "detail": exc.detail,
        },
    )


@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError) -> JSONResponse:
    """Catch stray ValueErrors and return 422."""
    logger.warning("ValueError in %s %s: %s", request.method, request.url, exc)
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error": True,
            "status_code": 422,
            "detail": str(exc),
        },
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(
    request: Request, exc: Exception
) -> JSONResponse:
    """Last-resort handler for unexpected exceptions."""
    logger.error(
        "Unhandled exception in %s %s: %s",
        request.method,
        request.url,
        exc,
        exc_info=True,
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": True,
            "status_code": 500,
            "detail": "An internal server error occurred. Please try again later.",
        },
    )
