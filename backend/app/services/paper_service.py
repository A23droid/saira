import uuid
from typing import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.paper import Paper
from app.schemas.paper import PaperCreate, PaperUpdate


class PaperService:
    async def create_paper(self, session: AsyncSession, paper_in: PaperCreate) -> Paper:
        paper = Paper(**paper_in.model_dump())
        session.add(paper)
        await session.commit()
        await session.refresh(paper)
        return paper

    async def get_all_papers(self, session: AsyncSession, skip: int = 0, limit: int = 100) -> Sequence[Paper]:
        stmt = select(Paper).offset(skip).limit(limit)
        result = await session.scalars(stmt)
        return result.all()

    async def get_paper_by_id(self, session: AsyncSession, paper_id: uuid.UUID) -> Paper | None:
        stmt = select(Paper).where(Paper.id == paper_id)
        return await session.scalar(stmt)

    async def update_paper(self, session: AsyncSession, db_paper: Paper, paper_in: PaperUpdate) -> Paper:
        update_data = paper_in.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(db_paper, field, value)

        await session.commit()
        await session.refresh(db_paper)
        return db_paper

    async def delete_paper(self, session: AsyncSession, db_paper: Paper) -> None:
        await session.delete(db_paper)
        await session.commit()


paper_service = PaperService()
