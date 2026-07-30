import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class AuthProvider:
    """Allowed values for `User.provider`. Not a DB enum on purpose — keeps
    adding a new provider a pure application-layer change (no migration)."""

    LOCAL = "local"
    GOOGLE = "google"
    ORCID = "orcid"

    ALL = (LOCAL, GOOGLE, ORCID)


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("email", name="uq_users_email"),
        UniqueConstraint("provider", "provider_id", name="uq_users_provider_provider_id"),
        CheckConstraint(
            "provider IN ('local', 'google', 'orcid')", name="ck_users_provider_valid"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(320), nullable=False, index=True)

    # Nullable: OAuth-only users (Google, ORCID) never set a local password.
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)

    provider: Mapped[str] = mapped_column(String(20), nullable=False, default=AuthProvider.LOCAL)
    # Provider Subject ID (Google `sub`) or ORCID iD — null for `local` users.
    provider_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)

    # Absolute URL to the user's avatar image. Populated either from an
    # uploaded file (see app/services/avatar_service.py) or, for Google
    # sign-ins, from the provider's profile picture at first login. Never
    # overwritten by a later Google login once a user has uploaded their
    # own image — see oauth_service.find_or_create_oauth_user.
    avatar_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    refresh_tokens: Mapped[list["RefreshToken"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid only
        return f"<User id={self.id} email={self.email!r} provider={self.provider!r}>"
