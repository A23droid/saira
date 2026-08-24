import uuid
from typing import Any, List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.api.deps import get_db, get_current_user
from app.models.user import User
from app.models.paper import Paper
from app.models.collection_paper import CollectionPaper
from app.schemas.collection import (
    CollectionCreate,
    CollectionUpdate,
    CollectionResponse,
    CollectionPaperResponse,
)
from app.schemas.paper import PaperResponse
from app.services.collection_service import collection_service
from app.services.paper_service import paper_service

router = APIRouter()


@router.post("/", response_model=CollectionResponse, status_code=status.HTTP_201_CREATED)
async def create_collection(
    collection_in: CollectionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    return await collection_service.create_collection(
        session=db, user_id=current_user.id, collection_in=collection_in
    )


@router.get("/", response_model=List[CollectionResponse])
async def get_collections(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    return await collection_service.get_all_collections(session=db, user_id=current_user.id)


@router.get("/{collection_id}", response_model=CollectionResponse)
async def get_collection(
    collection_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    collection = await collection_service.get_collection_by_id(
        session=db, collection_id=collection_id, user_id=current_user.id
    )
    if not collection:
        raise HTTPException(status_code=404, detail="Collection not found")
    return collection


@router.patch("/{collection_id}", response_model=CollectionResponse)
async def update_collection(
    collection_id: uuid.UUID,
    collection_in: CollectionUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    collection = await collection_service.get_collection_by_id(
        session=db, collection_id=collection_id, user_id=current_user.id
    )
    if not collection:
        raise HTTPException(status_code=404, detail="Collection not found")
    return await collection_service.update_collection(
        session=db, db_collection=collection, collection_in=collection_in
    )


@router.delete("/{collection_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_collection(
    collection_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    collection = await collection_service.get_collection_by_id(
        session=db, collection_id=collection_id, user_id=current_user.id
    )
    if not collection:
        raise HTTPException(status_code=404, detail="Collection not found")
    await collection_service.delete_collection(session=db, db_collection=collection)
    return None


@router.post("/{collection_id}/papers/{paper_id}", response_model=CollectionPaperResponse, status_code=status.HTTP_201_CREATED)
async def add_paper_to_collection(
    collection_id: uuid.UUID,
    paper_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    collection = await collection_service.get_collection_by_id(
        session=db, collection_id=collection_id, user_id=current_user.id
    )
    if not collection:
        raise HTTPException(status_code=404, detail="Collection not found")
        
    paper = await paper_service.get_paper_by_id(session=db, paper_id=paper_id)
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")
        
    return await collection_service.add_paper_to_collection(
        session=db, collection_id=collection_id, paper_id=paper_id
    )


@router.delete("/{collection_id}/papers/{paper_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_paper_from_collection(
    collection_id: uuid.UUID,
    paper_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    collection = await collection_service.get_collection_by_id(
        session=db, collection_id=collection_id, user_id=current_user.id
    )
    if not collection:
        raise HTTPException(status_code=404, detail="Collection not found")
        
    await collection_service.remove_paper_from_collection(
        session=db, collection_id=collection_id, paper_id=paper_id
    )
    return None


@router.get("/{collection_id}/papers", response_model=List[PaperResponse])
async def get_collection_papers(
    collection_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    collection = await collection_service.get_collection_by_id(
        session=db, collection_id=collection_id, user_id=current_user.id
    )
    if not collection:
        raise HTTPException(status_code=404, detail="Collection not found")
        
    stmt = (
        select(Paper)
        .join(CollectionPaper)
        .where(CollectionPaper.collection_id == collection_id)
        .order_by(CollectionPaper.added_at.desc())
    )
    result = await db.scalars(stmt)
    return result.all()
