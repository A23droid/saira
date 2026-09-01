from typing import TYPE_CHECKING
import uuid
from datetime import datetime

from sqlalchemy import Text, ForeignKey, func, DateTime
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class PaperAnalysis(Base):
    __tablename__ = "paper_analyses"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    paper_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("papers.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    
    summary_eli5: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary_student: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary_researcher: Mapped[str | None] = mapped_column(Text, nullable=True)
    
    should_read: Mapped[str | None] = mapped_column(Text, nullable=True)
    novelty: Mapped[str | None] = mapped_column(Text, nullable=True)
    research_gap: Mapped[str | None] = mapped_column(Text, nullable=True)
    
    datasets: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    models: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    algorithms: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    results: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    
    limitations: Mapped[str | None] = mapped_column(Text, nullable=True)
    future_work: Mapped[str | None] = mapped_column(Text, nullable=True)
    glossary: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    
    paper = relationship("Paper", backref="analysis")
    
    def __repr__(self) -> str:
        return f"<PaperAnalysis id={self.id} paper_id={self.paper_id}>"
