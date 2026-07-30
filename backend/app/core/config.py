"""
Centralized, environment-based configuration.

All runtime configuration is read from environment variables (optionally via
a `.env` file in local development). Nothing here should ever hold a real
secret — see `.env.example` for the variables this app expects.
"""

from functools import lru_cache
from typing import Literal

from pydantic import AnyHttpUrl, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- General -----------------------------------------------------
    PROJECT_NAME: str = "SAIRA API"
    API_V1_PREFIX: str = "/api/v1"
    ENVIRONMENT: Literal["development", "staging", "production", "test"] = "development"
    DEBUG: bool = True

    # --- CORS ----------------------------------------------------------
    # Comma-separated list of allowed origins, e.g. "http://localhost:3000,https://saira.app"
    BACKEND_CORS_ORIGINS: str = "http://localhost:3000"

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.BACKEND_CORS_ORIGINS.split(",") if o.strip()]

    # --- Database --------------------------------------------------------
    # Async URL used by the running application (asyncpg driver).
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/saira"
    DB_ECHO: bool = False
    DB_POOL_SIZE: int = 5
    DB_MAX_OVERFLOW: int = 10

    # --- JWT ---------------------------------------------------------------
    JWT_SECRET_KEY: str = "CHANGE_ME_IN_PRODUCTION"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30

    # --- Session (required by Authlib's OAuth state/nonce handling) -------
    SESSION_SECRET_KEY: str = "CHANGE_ME_IN_PRODUCTION"

    # --- Frontend --------------------------------------------------------
    # Where OAuth callbacks redirect back to once a session is established.
    FRONTEND_URL: str = "http://localhost:3000"

    # --- Media storage (avatar uploads) -------------------------------------
    # Local-disk storage for dev/small deployments: files live under
    # MEDIA_ROOT and are served back at {BACKEND_PUBLIC_URL}/media/... via a
    # StaticFiles mount (see app/main.py). Swapping to S3/GCS/Cloudinary
    # later only means changing app/services/avatar_service.py — everything
    # else (the column, the endpoint, the frontend) reads a plain URL and
    # doesn't care where it's actually hosted.
    MEDIA_ROOT: str = "media"
    BACKEND_PUBLIC_URL: str = "http://localhost:8000"
    AVATAR_MAX_SIZE_MB: float = 5.0

    @property
    def avatar_max_size_bytes(self) -> int:
        return int(self.AVATAR_MAX_SIZE_MB * 1024 * 1024)

    # --- Auth cookies ------------------------------------------------------
    # Left unset (host-only cookie) for local dev, where the frontend
    # (localhost:3000) and backend (localhost:8000) share the same hostname
    # and cookies ignore port when matching. For a production deployment
    # split across subdomains (e.g. app.saira.com / api.saira.com), set this
    # to ".saira.com" so the cookie is shared across both.
    COOKIE_DOMAIN: str | None = None

    @property
    def cookie_secure(self) -> bool:
        # `Secure` cookies are only sent over HTTPS. Local dev runs on plain
        # HTTP, so this must be False there or the browser silently drops it.
        return self.ENVIRONMENT != "development"

    # --- Google OAuth ------------------------------------------------------
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    GOOGLE_REDIRECT_URI: str = "http://localhost:8000/api/v1/auth/google/callback"

    # --- ORCID OAuth -------------------------------------------------------
    ORCID_CLIENT_ID: str = ""
    ORCID_CLIENT_SECRET: str = ""
    ORCID_REDIRECT_URI: str = "http://localhost:8000/api/v1/auth/orcid/callback"
    # ORCID has separate sandbox and production environments with different hosts.
    ORCID_ENVIRONMENT: Literal["sandbox", "production"] = "sandbox"

    @property
    def orcid_base_url(self) -> str:
        return (
            "https://sandbox.orcid.org"
            if self.ORCID_ENVIRONMENT == "sandbox"
            else "https://orcid.org"
        )

    @property
    def orcid_api_base_url(self) -> str:
        return (
            "https://api.sandbox.orcid.org"
            if self.ORCID_ENVIRONMENT == "sandbox"
            else "https://api.orcid.org"
        )

    @field_validator("JWT_SECRET_KEY", "SESSION_SECRET_KEY")
    @classmethod
    def _warn_on_default_secret(cls, value: str) -> str:
        # Left permissive on purpose (so the app still boots in dev / CI),
        # but this is the seam to enforce stricter checks in production.
        return value


@lru_cache
def get_settings() -> Settings:
    """Cached settings accessor — read once, reused across the app."""
    return Settings()


settings = get_settings()
