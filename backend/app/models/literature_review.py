import uuid
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class LiteratureReview(Base):
    """
    Stores a generated literature review for a project.

    paper_set_version is a SHA-256 fingerprint of the sorted paper IDs
    present at generation time. If this differs from the current paper set,
    the review is considered stale.
    """
    __tablename__ = "literature_reviews"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )

    # Fingerprint of sorted paper IDs at generation time
    paper_set_version: Mapped[str] = mapped_column(String(64), nullable=False)
    paper_count: Mapped[int] = mapped_column(Integer, nullable=False)

    # Full structured review output as JSONB
    content: Mapped[dict] = mapped_column(JSONB, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    project: Mapped["Project"] = relationship()
    user: Mapped["User"] = relationship()

    def __repr__(self) -> str:
        return f"<LiteratureReview id={self.id} project_id={self.project_id}>"
