import uuid
from typing import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.note import Note
from app.models.highlight import Highlight
from app.models.reading_progress import ReadingProgress
from app.schemas.reading_data import (
    NoteCreate, NoteUpdate,
    HighlightCreate, HighlightUpdate,
    ReadingProgressUpdate,
)


class ReadingDataService:
    # Notes
    async def create_note(self, session: AsyncSession, project_paper_id: uuid.UUID, note_in: NoteCreate) -> Note:
        note = Note(project_paper_id=project_paper_id, **note_in.model_dump())
        session.add(note)
        await session.commit()
        await session.refresh(note)
        return note

    async def update_note(self, session: AsyncSession, db_note: Note, note_in: NoteUpdate) -> Note:
        update_data = note_in.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(db_note, field, value)
        await session.commit()
        await session.refresh(db_note)
        return db_note

    async def delete_note(self, session: AsyncSession, db_note: Note) -> None:
        await session.delete(db_note)
        await session.commit()

    async def get_note(self, session: AsyncSession, note_id: uuid.UUID) -> Note | None:
        return await session.scalar(select(Note).where(Note.id == note_id))

    # Highlights
    async def create_highlight(self, session: AsyncSession, project_paper_id: uuid.UUID, highlight_in: HighlightCreate) -> Highlight:
        hl = Highlight(project_paper_id=project_paper_id, **highlight_in.model_dump())
        session.add(hl)
        await session.commit()
        await session.refresh(hl)
        return hl

    async def update_highlight(self, session: AsyncSession, db_hl: Highlight, highlight_in: HighlightUpdate) -> Highlight:
        update_data = highlight_in.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(db_hl, field, value)
        await session.commit()
        await session.refresh(db_hl)
        return db_hl

    async def delete_highlight(self, session: AsyncSession, db_hl: Highlight) -> None:
        await session.delete(db_hl)
        await session.commit()

    async def get_highlight(self, session: AsyncSession, highlight_id: uuid.UUID) -> Highlight | None:
        return await session.scalar(select(Highlight).where(Highlight.id == highlight_id))

    # Reading Progress (Upsert semantics)
    async def upsert_reading_progress(
        self, session: AsyncSession, project_paper_id: uuid.UUID, progress_in: ReadingProgressUpdate
    ) -> ReadingProgress:
        stmt = select(ReadingProgress).where(ReadingProgress.project_paper_id == project_paper_id)
        db_prog = await session.scalar(stmt)

        if not db_prog:
            db_prog = ReadingProgress(project_paper_id=project_paper_id)

        update_data = progress_in.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(db_prog, field, value)

        session.add(db_prog)
        await session.commit()
        await session.refresh(db_prog)
        return db_prog


reading_data_service = ReadingDataService()
