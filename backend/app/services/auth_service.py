import uuid
from datetime import datetime, timezone

import jwt
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession



from app.core.security import (
    TokenType,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    hash_token,
    verify_password,
)
from app.exceptions import InvalidCredentialsError, InvalidTokenError, TokenRevokedError, UserAlreadyExistsError
from app.models.refresh_token import RefreshToken
from app.models.user import AuthProvider, User
from app.schemas.auth import RegisterRequest
from app.schemas.token import TokenPair
from app.services import user_service


async def register_user(db: AsyncSession, payload: RegisterRequest) -> User:
    existing = await user_service.get_user_by_email(db, payload.email)
    if existing is not None:
        raise UserAlreadyExistsError()

    user = await user_service.create_user(
        db,
        name=payload.name,
        email=payload.email,
        provider=AuthProvider.LOCAL,
        password_hash=hash_password(payload.password),
    )
    await db.commit()
    return user


async def authenticate_local_user(db: AsyncSession, email: str, password: str) -> User:
    user = await user_service.get_user_by_email(db, email)

    # Constant-shape failure: don't reveal whether the email exists, and
    # don't let OAuth-only accounts (no password_hash) be brute-forced.
    if user is None or user.password_hash is None:
        raise InvalidCredentialsError()

    if not verify_password(password, user.password_hash):
        raise InvalidCredentialsError()

    return user


async def issue_token_pair(db: AsyncSession, user: User) -> TokenPair:
    access_token, _, _ = create_access_token(user.id)
    refresh_token, _, refresh_expires_at = create_refresh_token(user.id)

    db.add(
        RefreshToken(
            user_id=user.id,
            token_hash=hash_token(refresh_token),
            expires_at=refresh_expires_at,
        )
    )
    await db.commit()

    return TokenPair(access_token=access_token, refresh_token=refresh_token)


async def _get_valid_refresh_token_record(db: AsyncSession, raw_token: str) -> tuple[dict, RefreshToken]:
    try:
        payload = decode_token(raw_token)
    except jwt.PyJWTError as exc:
        raise InvalidTokenError() from exc

    if payload.get("type") != TokenType.REFRESH.value:
        raise InvalidTokenError("This endpoint requires a refresh token.")

    result = await db.execute(
        select(RefreshToken).where(RefreshToken.token_hash == hash_token(raw_token))
    )
    record = result.scalar_one_or_none()

    if record is None:
        raise InvalidTokenError()
    if record.revoked:
        raise TokenRevokedError()
    if record.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        raise InvalidTokenError("Refresh token has expired.")

    return payload, record


async def rotate_refresh_token(db: AsyncSession, raw_token: str) -> TokenPair:
    """Verify a refresh token, revoke it, and issue a brand new pair.

    Rotation means a stolen refresh token is only useful once — the moment
    either the legitimate client or an attacker uses it, the old token is
    dead and any later replay is rejected.
    """
    payload, record = await _get_valid_refresh_token_record(db, raw_token)

    user = await user_service.get_user_by_id(db, uuid.UUID(payload["sub"]))
    if user is None or not user.is_active:
        raise InvalidTokenError()

    record.revoked = True
    db.add(record)

    return await issue_token_pair(db, user)


async def revoke_refresh_token(db: AsyncSession, raw_token: str) -> None:
    """Used by the logout endpoint.

    Deliberately tolerant: logout should never fail from the caller's point
    of view. An already-invalid, expired, or foreign token is treated as
    "nothing to revoke" rather than an error — possession of the exact
    refresh token value (only ever readable from that user's own httpOnly
    cookie) is what authorizes the revocation, so no separate access-token
    check is required here.
    """
    try:
        payload = decode_token(raw_token)
    except jwt.PyJWTError:
        return

    if payload.get("type") != TokenType.REFRESH.value:
        return

    await db.execute(
        update(RefreshToken)
        .where(RefreshToken.token_hash == hash_token(raw_token))
        .values(revoked=True)
    )
    await db.commit()
