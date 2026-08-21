from authlib.integrations.starlette_client import OAuthError
from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import RedirectResponse

from app.core.config import settings
from app.core.cookies import set_auth_cookies
from app.core.oauth import oauth
from app.db.session import get_db
from app.exceptions import AppError, OAuthProviderError
from app.models.user import AuthProvider
from app.services.auth_service import issue_token_pair
from app.services.oauth_service import find_or_create_oauth_user

router = APIRouter(tags=["oauth-google"])


@router.get("/google/login")
async def google_login(request: Request) -> RedirectResponse:
    """Redirect the browser to Google's consent screen."""
    redirect_uri = settings.GOOGLE_REDIRECT_URI
    return await oauth.google.authorize_redirect(request, redirect_uri)


@router.get("/google/callback")
async def google_callback(request: Request, db: AsyncSession = Depends(get_db)) -> RedirectResponse:
    """
    Handle Google's redirect back to us: exchange the `code` for tokens,
    resolve (or create) the local user, set the session cookies, and send
    the browser on to the frontend dashboard.

    This is a real top-level browser navigation (the user's tab just came
    back from accounts.google.com), so on any failure we redirect to the
    frontend's login page with an `error` query param rather than returning
    a raw JSON error — there's no frontend code running on this response to
    parse it.
    """
    try:
        token = await oauth.google.authorize_access_token(request)

        userinfo = token.get("userinfo")
        if not userinfo or not userinfo.get("sub") or not userinfo.get("email"):
            raise OAuthProviderError("Google did not return the expected profile information.")

        user = await find_or_create_oauth_user(
            db,
            provider=AuthProvider.GOOGLE,
            provider_id=userinfo["sub"],
            email=userinfo["email"],
            name=userinfo.get("name") or userinfo["email"].split("@")[0],
            avatar_url=userinfo.get("picture"),
        )
        tokens = await issue_token_pair(db, user)
    except (OAuthError, AppError):
        return RedirectResponse(f"{settings.FRONTEND_URL}/login?error=oauth_failed", status_code=302)

    redirect = RedirectResponse(f"{settings.FRONTEND_URL}/dashboard", status_code=302)
    set_auth_cookies(redirect, tokens.access_token, tokens.refresh_token)
    return redirect
