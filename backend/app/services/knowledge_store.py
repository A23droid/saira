"""
Portable blob storage for compiled knowledge pages.

The knowledge store holds Markdown — one page per paper, plus aggregated
concept/method/topic pages and an index. It is the portable half of the
architecture: copy the tree to S3, read it by hand, diff it in git. Postgres
holds only the derived search index (see `knowledge_index.py`), which can be
rebuilt from these files at any time.

Two backends, one interface. Local disk for development and single-node
deployments; S3 for AWS. Nothing above this module knows which is in use —
callers pass logical paths like `papers/<uuid>.md` and never touch a
filesystem path or a bucket key.

ponytail: two backends because §10/§20 of the migration brief ask for local
dev and S3 deploy explicitly. No caching layer, no async filesystem library —
blocking I/O is pushed to a thread, which is enough at knowledge-page sizes.
"""

from __future__ import annotations

import asyncio
import logging
import re
from abc import ABC, abstractmethod
from pathlib import Path
from typing import List, Optional

from app.core.config import settings

logger = logging.getLogger(__name__)

#: Logical paths are validated rather than trusted. Paper IDs and concept
#: slugs both reach this module, and a `..` in either would escape the root.
_SAFE_PATH = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]*$")


class KnowledgeStoreError(Exception):
    """Raised when the store cannot satisfy a request."""


def _validate(path: str) -> str:
    if not path or ".." in path or path.startswith("/") or not _SAFE_PATH.match(path):
        raise KnowledgeStoreError(f"Unsafe knowledge path: {path!r}")
    return path


class KnowledgeStore(ABC):
    """Logical-path blob store. Paths are POSIX-style and relative."""

    @abstractmethod
    async def write(self, path: str, content: str) -> str:
        """Write UTF-8 text. Returns a locator for logging/debugging."""

    @abstractmethod
    async def read(self, path: str) -> Optional[str]:
        """Return the content, or None if it does not exist."""

    @abstractmethod
    async def delete(self, path: str) -> bool:
        """Delete if present. Returns whether anything was removed."""

    @abstractmethod
    async def list(self, prefix: str = "") -> List[str]:
        """List logical paths under a prefix."""


class LocalKnowledgeStore(KnowledgeStore):
    """Filesystem backend, rooted at `settings.KNOWLEDGE_ROOT`."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()

    def _full(self, path: str) -> Path:
        resolved = (self.root / _validate(path)).resolve()
        # Belt and braces: even with the regex, confirm we stayed inside.
        if not str(resolved).startswith(str(self.root)):
            raise KnowledgeStoreError(f"Path escapes knowledge root: {path!r}")
        return resolved

    def _write_sync(self, target: Path, content: str) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        # Write-then-rename so a reader never sees a half-written page.
        tmp = target.with_suffix(target.suffix + ".tmp")
        tmp.write_text(content, encoding="utf-8")
        tmp.replace(target)

    async def write(self, path: str, content: str) -> str:
        target = self._full(path)
        await asyncio.to_thread(self._write_sync, target, content)
        return str(target)

    async def read(self, path: str) -> Optional[str]:
        target = self._full(path)

        def _read() -> Optional[str]:
            if not target.is_file():
                return None
            return target.read_text(encoding="utf-8")

        return await asyncio.to_thread(_read)

    async def delete(self, path: str) -> bool:
        target = self._full(path)

        def _delete() -> bool:
            if not target.is_file():
                return False
            target.unlink()
            return True

        return await asyncio.to_thread(_delete)

    async def list(self, prefix: str = "") -> List[str]:
        base = self._full(prefix) if prefix else self.root

        def _list() -> List[str]:
            if not base.exists():
                return []
            if base.is_file():
                return [base.relative_to(self.root).as_posix()]
            return sorted(
                p.relative_to(self.root).as_posix()
                for p in base.rglob("*")
                if p.is_file() and not p.name.endswith(".tmp")
            )

        return await asyncio.to_thread(_list)


class S3KnowledgeStore(KnowledgeStore):
    """S3 backend. Keys are `{prefix}/{logical path}`.

    boto3 is imported lazily so the dependency is only required by deployments
    that actually select this backend — local development never pays for it.
    """

    def __init__(self, bucket: str, prefix: str = "knowledge") -> None:
        self.bucket = bucket
        self.prefix = prefix.strip("/")
        self._client = None

    def _get_client(self):
        if self._client is None:
            try:
                import boto3  # type: ignore
            except ImportError as exc:  # pragma: no cover - deploy-time config
                raise KnowledgeStoreError(
                    "KNOWLEDGE_STORE_BACKEND=s3 requires boto3. "
                    "Install it (pip install boto3) or use the local backend."
                ) from exc
            self._client = boto3.client("s3")
        return self._client

    def _key(self, path: str) -> str:
        return f"{self.prefix}/{_validate(path)}" if self.prefix else _validate(path)

    async def write(self, path: str, content: str) -> str:
        key = self._key(path)
        client = self._get_client()

        def _put() -> None:
            client.put_object(
                Bucket=self.bucket,
                Key=key,
                Body=content.encode("utf-8"),
                ContentType="text/markdown; charset=utf-8",
            )

        await asyncio.to_thread(_put)
        return f"s3://{self.bucket}/{key}"

    async def read(self, path: str) -> Optional[str]:
        key = self._key(path)
        client = self._get_client()

        def _get() -> Optional[str]:
            try:
                resp = client.get_object(Bucket=self.bucket, Key=key)
            except client.exceptions.NoSuchKey:
                return None
            return resp["Body"].read().decode("utf-8")

        return await asyncio.to_thread(_get)

    async def delete(self, path: str) -> bool:
        key = self._key(path)
        client = self._get_client()

        def _delete() -> bool:
            client.delete_object(Bucket=self.bucket, Key=key)
            return True

        return await asyncio.to_thread(_delete)

    async def list(self, prefix: str = "") -> List[str]:
        client = self._get_client()
        full_prefix = self._key(prefix) if prefix else self.prefix
        strip = len(self.prefix) + 1 if self.prefix else 0

        def _list() -> List[str]:
            keys: List[str] = []
            paginator = client.get_paginator("list_objects_v2")
            for page in paginator.paginate(Bucket=self.bucket, Prefix=full_prefix):
                for obj in page.get("Contents", []):
                    keys.append(obj["Key"][strip:])
            return sorted(keys)

        return await asyncio.to_thread(_list)


def _build_store() -> KnowledgeStore:
    backend = (settings.KNOWLEDGE_STORE_BACKEND or "local").lower()
    if backend == "s3":
        if not settings.KNOWLEDGE_S3_BUCKET:
            raise KnowledgeStoreError(
                "KNOWLEDGE_STORE_BACKEND=s3 requires KNOWLEDGE_S3_BUCKET."
            )
        logger.info(
            "knowledge_store backend=s3 bucket=%s prefix=%s",
            settings.KNOWLEDGE_S3_BUCKET, settings.KNOWLEDGE_S3_PREFIX,
        )
        return S3KnowledgeStore(settings.KNOWLEDGE_S3_BUCKET, settings.KNOWLEDGE_S3_PREFIX)
    if backend != "local":
        raise KnowledgeStoreError(f"Unknown KNOWLEDGE_STORE_BACKEND: {backend!r}")
    logger.info("knowledge_store backend=local root=%s", settings.KNOWLEDGE_ROOT)
    return LocalKnowledgeStore(settings.KNOWLEDGE_ROOT)


knowledge_store: KnowledgeStore = _build_store()


# ── Logical path helpers ──────────────────────────────────────────────────────
# One place that decides what the tree looks like, so the layout in the docs
# and the layout on disk cannot drift.

def paper_page_path(paper_id: str) -> str:
    return f"papers/{paper_id}.md"


def concept_page_path(slug: str) -> str:
    return f"concepts/{slug}.md"


def method_page_path(slug: str) -> str:
    return f"methods/{slug}.md"


def topic_page_path(slug: str) -> str:
    return f"topics/{slug}.md"


def index_page_path() -> str:
    return "index.md"
