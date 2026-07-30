"""
Avatar file storage.

Files are saved to local disk under `settings.MEDIA_ROOT` and served back
by the static mount in `app.main`. This is the one module that would need
to change to move to S3/GCS/Cloudinary/etc. in production — everywhere
else in the app just reads and writes a plain `avatar_url` string, so that
swap doesn't touch models, schemas, or the frontend at all.

Deliberately not storing the raw upload as-is: every image is decoded with
Pillow (which both validates it's a genuine, undamaged image — not just a
file with a misleading extension/content-type — and lets us normalize it),
downscaled to a max of 512x512, and re-encoded as PNG under a filename
keyed by user ID. That last part means a re-upload cleanly replaces the
previous avatar file rather than accumulating orphaned images.
"""

import time
import uuid
from io import BytesIO
from pathlib import Path

from fastapi import UploadFile
from PIL import Image, UnidentifiedImageError

from app.core.config import settings
from app.exceptions import InvalidImageError, PayloadTooLargeError, UnsupportedMediaTypeError

ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}
MAX_DIMENSION = 512
_CHUNK_SIZE = 1024 * 1024  # 1 MB


async def _read_upload_within_limit(file: UploadFile) -> bytes:
    """Read the upload in chunks, bailing out as soon as it exceeds the
    configured size limit rather than trusting the client-declared size."""
    limit = settings.avatar_max_size_bytes
    chunks: list[bytes] = []
    total = 0

    while True:
        chunk = await file.read(_CHUNK_SIZE)
        if not chunk:
            break
        total += len(chunk)
        if total > limit:
            raise PayloadTooLargeError(
                f"Avatar images must be under {settings.AVATAR_MAX_SIZE_MB:.0f}MB."
            )
        chunks.append(chunk)

    return b"".join(chunks)


async def save_avatar(user_id: uuid.UUID, file: UploadFile) -> str:
    """Validate, normalize, and persist an uploaded avatar. Returns the
    public URL to store on the user's `avatar_url`."""
    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise UnsupportedMediaTypeError()

    raw_bytes = await _read_upload_within_limit(file)

    try:
        image = Image.open(BytesIO(raw_bytes))
        image.load()  # forces full decode now, not lazily later — catches corrupt files here
    except UnidentifiedImageError as exc:
        raise InvalidImageError() from exc

    image = image.convert("RGBA") if image.mode in ("RGBA", "LA", "P") else image.convert("RGB")
    image.thumbnail((MAX_DIMENSION, MAX_DIMENSION), Image.LANCZOS)

    avatars_dir = Path(settings.MEDIA_ROOT) / "avatars"
    avatars_dir.mkdir(parents=True, exist_ok=True)

    filename = f"{user_id}.png"
    image.save(avatars_dir / filename, format="PNG", optimize=True)

    # Cache-bust: the filename is stable per user (so re-uploads replace
    # cleanly), so without a version param the browser would keep showing
    # a stale cached copy after a new upload.
    return f"{settings.BACKEND_PUBLIC_URL}/media/avatars/{filename}?v={int(time.time())}"
