import uuid
from typing import Optional, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.collection import Collection
from app.models.collection_paper import CollectionPaper
from app.schemas.collection import CollectionCreate, CollectionUpdate

class CollectionService:
    async def create_collection(
        self, session: AsyncSession, user_id: uuid.UUID, collection_in: CollectionCreate
    ) -> Collection:
        collection = Collection(user_id=user_id, **collection_in.model_dump())
        session.add(collection)
        await session.commit()
        await session.refresh(collection)
        return collection

    async def get_collection_by_id(
        self, session: AsyncSession, collection_id: uuid.UUID, user_id: uuid.UUID
    ) -> Optional[Collection]:
        stmt = select(Collection).where(
            Collection.id == collection_id, Collection.user_id == user_id
        )
        return await session.scalar(stmt)

    async def get_all_collections(
        self, session: AsyncSession, user_id: uuid.UUID
    ) -> Sequence[Collection]:
        stmt = select(Collection).where(Collection.user_id == user_id).order_by(Collection.created_at.desc())
        result = await session.scalars(stmt)
        return result.all()

    async def update_collection(
        self, session: AsyncSession, db_collection: Collection, collection_in: CollectionUpdate
    ) -> Collection:
        update_data = collection_in.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(db_collection, field, value)
        await session.commit()
        await session.refresh(db_collection)
        return db_collection

    async def delete_collection(self, session: AsyncSession, db_collection: Collection) -> None:
        await session.delete(db_collection)
        await session.commit()

    async def add_paper_to_collection(
        self, session: AsyncSession, collection_id: uuid.UUID, paper_id: uuid.UUID
    ) -> CollectionPaper:
        stmt = select(CollectionPaper).where(
            CollectionPaper.collection_id == collection_id,
            CollectionPaper.paper_id == paper_id,
        )
        existing = await session.scalar(stmt)
        if existing:
            return existing
            
        cp = CollectionPaper(collection_id=collection_id, paper_id=paper_id)
        session.add(cp)
        await session.commit()
        await session.refresh(cp)
        return cp

    async def remove_paper_from_collection(
        self, session: AsyncSession, collection_id: uuid.UUID, paper_id: uuid.UUID
    ) -> None:
        stmt = select(CollectionPaper).where(
            CollectionPaper.collection_id == collection_id,
            CollectionPaper.paper_id == paper_id,
        )
        cp = await session.scalar(stmt)
        if cp:
            await session.delete(cp)
            await session.commit()

collection_service = CollectionService()
