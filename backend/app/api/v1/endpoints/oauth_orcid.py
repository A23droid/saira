from authlib.integrations.starlette_client import OAuthError
from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import RedirectResponse

from app.core.config import settings
from app.core.oauth import oauth
from app.db.session import get_db
from app.exceptions import OAuthProviderError
from app.models.user import AuthProvider
from app.schemas.token import TokenPair
from app.services.auth_service import issue_token_pair
from app.services.oauth_service import find_or_create_oauth_user

router = APIRouter(tags=["oauth-orcid"])


@router.get("/orcid/login")
async def orcid_login(request: Request) -> RedirectResponse:
    """Redirect the browser to ORCID's consent screen."""
    redirect_uri = settings.ORCID_REDIRECT_URI
    return await oauth.orcid.authorize_redirect(request, redirect_uri)


@router.get("/orcid/callback", response_model=TokenPair)
async def orcid_callback(request: Request, db: AsyncSession = Depends(get_db)) -> TokenPair:
    """
    Handle ORCID's redirect back to us.

    Unlike Google, ORCID's "Authenticate with ORCID" flow is plain OAuth2
    (not OpenID Connect): the token endpoint response itself already
    contains the `orcid` iD and the person's `name`, so no separate
    userinfo request is needed.
    """
    try:
        token = await oauth.orcid.authorize_access_token(request)
    except OAuthError as exc:
        raise OAuthProviderError(str(exc)) from exc

    orcid_id = token.get("orcid")
    if not orcid_id:
        raise OAuthProviderError("ORCID did not return an iD in the token response.")

    name = token.get("name") or f"ORCID {orcid_id}"
    # ORCID's basic authenticate flow does not grant an email address by
    # default (that requires a separate, member-only scope). We synthesize
    # a stable, unique placeholder so the `email` column's uniqueness
    # constraint is preserved without blocking sign-in.
    email = token.get("email") or f"{orcid_id}@orcid.users.saira.app"

    user = await find_or_create_oauth_user(
        db,
        provider=AuthProvider.ORCID,
        provider_id=orcid_id,
        email=email,
        name=name,
    )
    return await issue_token_pair(db, user)
