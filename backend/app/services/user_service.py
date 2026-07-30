import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User


async def get_user_by_id(db: AsyncSession, user_id: uuid.UUID | str) -> User | None:
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


async def get_user_by_email(db: AsyncSession, email: str) -> User | None:
    result = await db.execute(select(User).where(User.email == email.lower()))
    return result.scalar_one_or_none()


async def get_user_by_provider(db: AsyncSession, provider: str, provider_id: str) -> User | None:
    result = await db.execute(
        select(User).where(User.provider == provider, User.provider_id == provider_id)
    )
    return result.scalar_one_or_none()


async def create_user(
    db: AsyncSession,
    *,
    name: str,
    email: str,
    provider: str,
    password_hash: str | None = None,
    provider_id: str | None = None,
    avatar_url: str | None = None,
) -> User:
    user = User(
        name=name,
        email=email.lower(),
        password_hash=password_hash,
        provider=provider,
        provider_id=provider_id,
        avatar_url=avatar_url,
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)
    return user


async def update_user_name(db: AsyncSession, user: User, name: str) -> User:
    user.name = name
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def set_user_avatar_url(db: AsyncSession, user: User, avatar_url: str) -> User:
    user.avatar_url = avatar_url
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user
