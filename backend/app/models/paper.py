from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.project_paper import ProjectPaper

import uuid
from datetime import datetime

from sqlalchemy import Integer, String, Text, func, DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Paper(Base):
    __tablename__ = "papers"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    doi: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True)
    arxiv_id: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True)
    semantic_scholar_id: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True)
    
    title: Mapped[str] = mapped_column(Text, nullable=False)
    abstract: Mapped[str | None] = mapped_column(Text, nullable=True)
    
    publication_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    venue: Mapped[str | None] = mapped_column(String(255), nullable=True)
    
    pdf_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str | None] = mapped_column(String(255), nullable=True)
    
    citation_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reference_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    project_papers: Mapped[list["ProjectPaper"]] = relationship(
        back_populates="paper", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Paper id={self.id} title={self.title!r}>"
