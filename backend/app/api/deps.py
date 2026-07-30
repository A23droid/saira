import uuid

import jwt
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cookies import ACCESS_TOKEN_COOKIE
from app.core.security import TokenType, decode_token
from app.db.session import get_db
from app.exceptions import InactiveUserError, InvalidTokenError, NotAuthenticatedError, UserNotFoundError
from app.models.user import User
from app.services import user_service

# `auto_error=False` so we can raise our own `NotAuthenticatedError` (and get
# a consistent {"detail": ...} body) instead of FastAPI's default 403. Also
# lets the Authorization header be optional, since the cookie is the primary
# transport for browser clients.
bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Resolve the caller's `User` from an access token.

    Browser clients authenticate via the `access_token` HttpOnly cookie set
    at login. The `Authorization: Bearer <token>` header is also honored —
    checked first — so the API remains directly testable from curl/Swagger
    without a cookie jar.
    """
    token = credentials.credentials if credentials else request.cookies.get(ACCESS_TOKEN_COOKIE)

    if not token:
        raise NotAuthenticatedError()

    try:
        payload = decode_token(token)
    except jwt.PyJWTError as exc:
        raise InvalidTokenError() from exc

    if payload.get("type") != TokenType.ACCESS.value:
        raise InvalidTokenError("This endpoint requires an access token.")

    try:
        user_id = uuid.UUID(payload["sub"])
    except (KeyError, ValueError) as exc:
        raise InvalidTokenError() from exc

    user = await user_service.get_user_by_id(db, user_id)
    if user is None:
        raise UserNotFoundError()
    if not user.is_active:
        raise InactiveUserError()

    return user
