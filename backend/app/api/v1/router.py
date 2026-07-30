from fastapi import APIRouter

from app.api.v1.endpoints import auth, oauth_google, oauth_orcid

api_router = APIRouter()

api_router.include_router(auth.router, prefix="/auth")
api_router.include_router(oauth_google.router, prefix="/auth")
api_router.include_router(oauth_orcid.router, prefix="/auth")
