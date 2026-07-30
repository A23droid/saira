from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import EmailProviderConflictError
from app.models.user import User
from app.services import user_service


async def find_or_create_oauth_user(
    db: AsyncSession,
    *,
    provider: str,
    provider_id: str,
    email: str,
    name: str,
    avatar_url: str | None = None,
) -> User:
    """
    Resolve an OAuth callback to a local `User` row.

    Lookup order:
      1. Exact (provider, provider_id) match — the returning-user path.
      2. Existing account with the same email but a *different* provider —
         treated as a conflict rather than silently merged, since we have
         no way to prove the person requesting sign-in now is the same
         person who registered that email originally.
      3. Otherwise, create a brand new account for this provider.

    `avatar_url` (the provider's profile picture, if any) is only used at
    creation time. A returning user's `avatar_url` is never overwritten by
    a later login, since they may have since uploaded their own image —
    see the avatar upload endpoint in `api/v1/endpoints/auth.py`.
    """
    existing_by_provider = await user_service.get_user_by_provider(db, provider, provider_id)
    if existing_by_provider is not None:
        return existing_by_provider

    existing_by_email = await user_service.get_user_by_email(db, email)
    if existing_by_email is not None:
        if existing_by_email.provider != provider:
            raise EmailProviderConflictError()
        return existing_by_email

    user = await user_service.create_user(
        db,
        name=name,
        email=email,
        provider=provider,
        provider_id=provider_id,
        avatar_url=avatar_url,
    )
    await db.commit()
    return user
