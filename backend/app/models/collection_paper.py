from typing import TYPE_CHECKING
import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, func, DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.collection import Collection
    from app.models.paper import Paper

class CollectionPaper(Base):
    __tablename__ = "collection_papers"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    collection_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("collections.id", ondelete="CASCADE"), nullable=False)
    paper_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("papers.id", ondelete="CASCADE"), nullable=False)
    
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    collection: Mapped["Collection"] = relationship(back_populates="collection_papers")
    paper: Mapped["Paper"] = relationship(back_populates="collection_papers")

    def __repr__(self) -> str:
        return f"<CollectionPaper id={self.id} collection_id={self.collection_id} paper_id={self.paper_id}>"
