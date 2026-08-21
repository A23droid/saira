from fastapi import APIRouter

from app.api.v1.endpoints import auth, oauth_google, oauth_orcid, projects, papers, search

api_router = APIRouter()

api_router.include_router(auth.router, prefix="/auth")
api_router.include_router(oauth_google.router, prefix="/auth")
api_router.include_router(oauth_orcid.router, prefix="/auth")
api_router.include_router(projects.router, prefix="/projects", tags=["projects"])
api_router.include_router(papers.router, prefix="/papers", tags=["papers"])
api_router.include_router(search.router, prefix="/search", tags=["search"])
