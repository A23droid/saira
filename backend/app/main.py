from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.api.v1.router import api_router
from app.core.config import settings
from app.middleware.error_handler import register_exception_handlers

app = FastAPI(
    title=settings.PROJECT_NAME,
    debug=settings.DEBUG,
    openapi_url=f"{settings.API_V1_PREFIX}/openapi.json",
    docs_url=f"{settings.API_V1_PREFIX}/docs",
    redoc_url=f"{settings.API_V1_PREFIX}/redoc",
)

# Required by Authlib's Starlette integration to persist OAuth `state`/`nonce`
# between the /login redirect and the /callback request.
app.add_middleware(SessionMiddleware, secret_key=settings.SESSION_SECRET_KEY)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_exception_handlers(app)

app.include_router(api_router, prefix=settings.API_V1_PREFIX)

# Serves uploaded avatar files (see app/services/avatar_service.py). Plain
# <img> tags don't need CORS headers to load cross-origin, so no extra
# config is required for the frontend to display these.
media_root = Path(settings.MEDIA_ROOT)
media_root.mkdir(parents=True, exist_ok=True)
app.mount("/media", StaticFiles(directory=str(media_root)), name="media")


@app.get("/health", tags=["health"])
async def health_check() -> dict[str, str]:
    """Liveness probe — no DB access, so it stays fast and dependency-free."""
    return {"status": "ok", "environment": settings.ENVIRONMENT}
