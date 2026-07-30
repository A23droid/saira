"""
Security primitives: password hashing and JWT creation/verification.

Password hashing uses Argon2id (via passlib), the algorithm currently
recommended by OWASP for new applications — memory-hard and resistant to
GPU/ASIC cracking, unlike bcrypt/PBKDF2.

JWTs are signed with HS256 using a shared secret (`JWT_SECRET_KEY`). Access
and refresh tokens are both JWTs, distinguished by a `type` claim, so a
refresh token can never be replayed as an access token or vice versa.
"""

import hashlib
import uuid
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any

import jwt
from passlib.context import CryptContext

from app.core.config import settings

pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")


class TokenType(str, Enum):
    ACCESS = "access"
    REFRESH = "refresh"


def hash_password(plain_password: str) -> str:
    return pwd_context.hash(plain_password)


def verify_password(plain_password: str, password_hash: str) -> bool:
    return pwd_context.verify(plain_password, password_hash)


def hash_token(raw_token: str) -> str:
    """SHA-256 digest of a token, used so raw refresh tokens are never
    persisted — only their hash, which is useless to an attacker who
    only has DB access (they'd still need the original JWT)."""
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def _create_token(
    subject: str,
    token_type: TokenType,
    expires_delta: timedelta,
    extra_claims: dict[str, Any] | None = None,
) -> tuple[str, str, datetime]:
    """Build and sign a JWT. Returns (token, jti, expires_at)."""
    now = datetime.now(timezone.utc)
    expires_at = now + expires_delta
    jti = str(uuid.uuid4())

    payload: dict[str, Any] = {
        "sub": subject,
        "type": token_type.value,
        "iat": now,
        "exp": expires_at,
        "jti": jti,
    }
    if extra_claims:
        payload.update(extra_claims)

    token = jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    return token, jti, expires_at


def create_access_token(user_id: uuid.UUID | str) -> tuple[str, str, datetime]:
    return _create_token(
        subject=str(user_id),
        token_type=TokenType.ACCESS,
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    )


def create_refresh_token(user_id: uuid.UUID | str) -> tuple[str, str, datetime]:
    return _create_token(
        subject=str(user_id),
        token_type=TokenType.REFRESH,
        expires_delta=timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
    )


def decode_token(token: str) -> dict[str, Any]:
    """Decode and verify a JWT's signature and expiry.

    Raises `jwt.PyJWTError` subclasses on any failure — callers translate
    those into the appropriate HTTP error via `app.exceptions`.
    """
    return jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
