from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.project import Project
    from app.models.paper import Paper
    from app.models.note import Note
    from app.models.highlight import Highlight
    from app.models.reading_progress import ReadingProgress

import uuid
from datetime import datetime

from sqlalchemy import Integer, String, Text, ForeignKey, func, Boolean, DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class ProjectPaper(Base):
    __tablename__ = "project_papers"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    paper_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("papers.id", ondelete="CASCADE"), nullable=False
    )
    
    status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    favorite: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    priority: Mapped[int | None] = mapped_column(Integer, nullable=True)

    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    project: Mapped["Project"] = relationship(back_populates="project_papers")
    paper: Mapped["Paper"] = relationship(back_populates="project_papers")

    notes: Mapped[list["Note"]] = relationship(
        back_populates="project_paper", cascade="all, delete-orphan"
    )
    highlights: Mapped[list["Highlight"]] = relationship(
        back_populates="project_paper", cascade="all, delete-orphan"
    )
    reading_progress: Mapped[list["ReadingProgress"]] = relationship(
        back_populates="project_paper", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<ProjectPaper id={self.id} project_id={self.project_id} paper_id={self.paper_id}>"
