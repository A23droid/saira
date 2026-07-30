from fastapi import APIRouter, Depends, File, Request, Response, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.cookies import REFRESH_TOKEN_COOKIE, clear_auth_cookies, set_auth_cookies
from app.db.session import get_db
from app.exceptions import NotAuthenticatedError
from app.models.user import User
from app.schemas.auth import LoginRequest, RegisterRequest
from app.schemas.token import Message
from app.schemas.user import UserRead, UserUpdateRequest
from app.services import auth_service, avatar_service, user_service

router = APIRouter(tags=["auth"])


@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def register(
    payload: RegisterRequest, response: Response, db: AsyncSession = Depends(get_db)
) -> User:
    """Create a new email/password account and establish a session for it.

    Registering logs the person in immediately — the access/refresh cookies
    are set on this response, the same as `/login` — so the frontend can go
    straight from the sign-up form to the dashboard without a second request.
    """
    user = await auth_service.register_user(db, payload)
    tokens = await auth_service.issue_token_pair(db, user)
    set_auth_cookies(response, tokens.access_token, tokens.refresh_token)
    return user


@router.post("/login", response_model=UserRead)
async def login(
    payload: LoginRequest, response: Response, db: AsyncSession = Depends(get_db)
) -> User:
    """Exchange email + password for a session, set as HttpOnly cookies."""
    user = await auth_service.authenticate_local_user(db, payload.email, payload.password)
    tokens = await auth_service.issue_token_pair(db, user)
    set_auth_cookies(response, tokens.access_token, tokens.refresh_token)
    return user


@router.post("/refresh", response_model=Message)
async def refresh(
    request: Request, response: Response, db: AsyncSession = Depends(get_db)
) -> Message:
    """Rotate the session using the `refresh_token` cookie.

    Reads the refresh token from the cookie rather than a JSON body — the
    frontend never sees the raw token value, so there's nothing for it to
    forward. On success, both cookies are replaced with a new pair; the one
    just used is revoked (rotation), so it can't be replayed.
    """
    raw_refresh_token = request.cookies.get(REFRESH_TOKEN_COOKIE)
    if not raw_refresh_token:
        raise NotAuthenticatedError("No active session to refresh.")

    tokens = await auth_service.rotate_refresh_token(db, raw_refresh_token)
    set_auth_cookies(response, tokens.access_token, tokens.refresh_token)
    return Message(detail="Session refreshed.")


@router.post("/logout", response_model=Message)
async def logout(
    request: Request, response: Response, db: AsyncSession = Depends(get_db)
) -> Message:
    """End the session: revoke the refresh token (if any) and clear both cookies.

    Deliberately does not require a valid access token — someone whose
    access token has already expired should still be able to log out.
    """
    raw_refresh_token = request.cookies.get(REFRESH_TOKEN_COOKIE)
    if raw_refresh_token:
        await auth_service.revoke_refresh_token(db, raw_refresh_token)

    clear_auth_cookies(response)
    return Message(detail="Logged out successfully.")


@router.get("/me", response_model=UserRead)
async def get_me(current_user: User = Depends(get_current_user)) -> User:
    """Return the profile of the currently authenticated user."""
    return current_user


@router.patch("/me", response_model=UserRead)
async def update_me(
    payload: UserUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> User:
    """Update editable profile fields (currently just `name`).

    Email, provider, and account-creation date are intentionally not
    editable here — see `UserUpdateRequest` for why.
    """
    return await user_service.update_user_name(db, current_user, payload.name)


@router.post("/me/avatar", response_model=UserRead)
async def upload_avatar(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> User:
    """Upload (or replace) the current user's avatar image.

    Works the same way whether the account is a local email/password
    account or a Google account that already has a provider-supplied
    picture — a fresh upload always takes precedence from this point on.
    """
    avatar_url = await avatar_service.save_avatar(current_user.id, file)
    return await user_service.set_user_avatar_url(db, current_user, avatar_url)
