"""
HttpOnly cookie helpers for browser-based sessions.

Access and refresh tokens are still plain JWTs (see `app.core.security`);
what changes here is *transport*. Instead of handing them to the frontend
as JSON to be stored in `localStorage` — readable by any script on the
page, and therefore exposed to XSS — they're set as `HttpOnly` cookies the
browser attaches automatically and JavaScript can never read.

Both cookies are `SameSite=Lax`, which is enough here: the frontend
(`localhost:3000`) and backend (`localhost:8000`) are cross-origin but
same-site (cookies ignore port), so `Lax` still sends them on the fetch
calls the frontend makes — no need to drop to `SameSite=None` (which would
additionally require `Secure`, i.e. HTTPS, and isn't available for plain
local HTTP development).
"""

from fastapi import Response

from app.core.config import settings

ACCESS_TOKEN_COOKIE = "access_token"
REFRESH_TOKEN_COOKIE = "refresh_token"

_ACCESS_TOKEN_MAX_AGE = settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
_REFRESH_TOKEN_MAX_AGE = settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60


def set_auth_cookies(response: Response, access_token: str, refresh_token: str) -> None:
    """Attach both auth cookies to an outgoing response."""
    response.set_cookie(
        key=ACCESS_TOKEN_COOKIE,
        value=access_token,
        max_age=_ACCESS_TOKEN_MAX_AGE,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        domain=settings.COOKIE_DOMAIN,
        path="/",
    )
    response.set_cookie(
        key=REFRESH_TOKEN_COOKIE,
        value=refresh_token,
        max_age=_REFRESH_TOKEN_MAX_AGE,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        domain=settings.COOKIE_DOMAIN,
        path="/",
    )


def clear_auth_cookies(response: Response) -> None:
    """Remove both auth cookies — used on logout."""
    response.delete_cookie(
        key=ACCESS_TOKEN_COOKIE, domain=settings.COOKIE_DOMAIN, path="/"
    )
    response.delete_cookie(
        key=REFRESH_TOKEN_COOKIE, domain=settings.COOKIE_DOMAIN, path="/"
    )
