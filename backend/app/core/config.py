"""
Lumenis AI — Application Configuration

Centralised settings powered by pydantic-settings.
Values are read from environment variables and/or a `.env` file
located at the project root.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Project root is two levels up from this file:
#   backend/app/core/config.py  →  project root
_PROJECT_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    """Typed, validated application settings with sensible defaults."""

    model_config = SettingsConfigDict(
        env_file=str(_PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Google Gemini ──────────────────────────────────────────────
    GEMINI_API_KEY: str = Field(default="", description="Google Gemini API key")

    # ── PostgreSQL ─────────────────────────────────────────────────
    DATABASE_URL: str = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/lumenis",
        description="Async PostgreSQL connection string",
    )

    # ── Redis ──────────────────────────────────────────────────────
    REDIS_URL: str = Field(
        default="redis://localhost:6379/0",
        description="Redis connection URL (broker + cache)",
    )

    # ── Qdrant Vector Store ────────────────────────────────────────
    QDRANT_HOST: str = Field(default="localhost", description="Qdrant server host")
    QDRANT_PORT: int = Field(default=6333, description="Qdrant gRPC port")

    # ── Security ───────────────────────────────────────────────────
    SECRET_KEY: str = Field(
        default="change-me-to-a-random-secret-key",
        description="Secret key for JWT signing and general crypto",
    )

    # ── CORS ───────────────────────────────────────────────────────
    CORS_ORIGINS: str = Field(
        default="http://localhost:3000",
        description="Comma-separated allowed origins",
    )

    # ── File Uploads ───────────────────────────────────────────────
    UPLOAD_DIR: str = Field(default="./uploads", description="Directory for uploaded files")
    MAX_FILE_SIZE_MB: int = Field(default=50, description="Max upload size in megabytes")

    # ── Computed helpers ───────────────────────────────────────────

    @computed_field  # type: ignore[prop-decorator]
    @property
    def cors_origin_list(self) -> list[str]:
        """Parse comma-separated CORS origins into a list."""
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def database_url_sync(self) -> str:
        """Return a synchronous database URL (for Alembic migrations)."""
        return self.DATABASE_URL.replace("+asyncpg", "")

    @computed_field  # type: ignore[prop-decorator]
    @property
    def max_file_size_bytes(self) -> int:
        """Max upload size converted to bytes."""
        return self.MAX_FILE_SIZE_MB * 1024 * 1024

    @computed_field  # type: ignore[prop-decorator]
    @property
    def upload_path(self) -> Path:
        """Resolved upload directory as a Path object."""
        path = Path(self.UPLOAD_DIR)
        path.mkdir(parents=True, exist_ok=True)
        return path.resolve()


# ── Singleton ──────────────────────────────────────────────────────
settings = Settings()
