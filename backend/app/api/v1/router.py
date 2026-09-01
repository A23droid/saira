from fastapi import APIRouter

from app.api.v1.endpoints import (
    auth, oauth_google, oauth_orcid, projects, papers, search, ai, collections, chat, comparisons, project_ai,
    history, analytics, trending
)

api_router = APIRouter()

api_router.include_router(auth.router, prefix="/auth")
api_router.include_router(oauth_google.router, prefix="/auth")
api_router.include_router(oauth_orcid.router, prefix="/auth")
api_router.include_router(projects.router, prefix="/projects", tags=["projects"])
api_router.include_router(papers.router, prefix="/papers", tags=["papers"])
api_router.include_router(search.router, prefix="/search", tags=["search"])
api_router.include_router(ai.router, prefix="/ai", tags=["ai"])
api_router.include_router(collections.router, prefix="/collections", tags=["collections"])
api_router.include_router(chat.router, prefix="/chat", tags=["chat"])
api_router.include_router(comparisons.router, prefix="/comparisons", tags=["comparisons"])
api_router.include_router(project_ai.router, prefix="/projects", tags=["project-ai"])
api_router.include_router(history.router, prefix="/history", tags=["history"])
api_router.include_router(analytics.router, prefix="/analytics", tags=["analytics"])
api_router.include_router(trending.router, prefix="/trending", tags=["trending"])
