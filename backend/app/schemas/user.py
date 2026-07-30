import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserRead(BaseModel):
    """Public shape of a user — never includes `password_hash`."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    email: EmailStr
    provider: str
    avatar_url: str | None
    is_active: bool
    created_at: datetime


class UserUpdateRequest(BaseModel):
    """Editable profile fields. Email, provider, and account metadata are
    intentionally not here — email changes need their own verification
    flow (out of scope for now), and provider/created_at are immutable
    facts about the account, not preferences."""

    name: str = Field(min_length=1, max_length=255)
