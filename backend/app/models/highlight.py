import uuid
from datetime import datetime

from sqlalchemy import DateTime, Integer, Text, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Highlight(Base):
    __tablename__ = "highlights"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_paper_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("project_papers.id", ondelete="CASCADE"), nullable=False
    )
    
    page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    selected_text: Mapped[str] = mapped_column(Text, nullable=False)
    ai_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    project_paper: Mapped["ProjectPaper"] = relationship(back_populates="highlights")

    def __repr__(self) -> str:
        return f"<Highlight id={self.id}>"
