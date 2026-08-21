import uuid
from datetime import datetime

from sqlalchemy import DateTime, Integer, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class ReadingProgress(Base):
    __tablename__ = "reading_progress"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_paper_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("project_papers.id", ondelete="CASCADE"), nullable=False
    )
    
    progress_percent: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_page: Mapped[int | None] = mapped_column(Integer, nullable=True)

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_opened: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    project_paper: Mapped["ProjectPaper"] = relationship(back_populates="reading_progress")

    def __repr__(self) -> str:
        return f"<ReadingProgress id={self.id} percent={self.progress_percent}>"
