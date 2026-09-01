import uuid
from typing import Any
from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_current_user
from app.models.user import User
from app.models.user_history import UserHistory
from app.schemas.history import HistoryEventCreate, FrontendHistoryEvent

router = APIRouter()

@router.get("", response_model=list[FrontendHistoryEvent])
async def get_history(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    stmt = select(UserHistory).where(UserHistory.user_id == current_user.id).order_by(UserHistory.created_at.desc()).limit(100)
    result = await db.scalars(stmt)
    events = result.all()
    
    frontend_events = []
    for ev in events:
        title = "Activity"
        url = None
        desc = None
        
        if ev.metadata_json:
            title = ev.metadata_json.get("title", title)
            url = ev.metadata_json.get("url")
            desc = ev.metadata_json.get("description")
            
        frontend_events.append(
            FrontendHistoryEvent(
                id=str(ev.id),
                type=ev.event_type,
                timestamp=ev.created_at.isoformat(),
                title=title,
                description=desc,
                url=url
            )
        )
    return frontend_events

@router.post("", response_model=FrontendHistoryEvent)
async def create_history_event(
    event_in: HistoryEventCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    # Build metadata from the incoming request (frontend can pass title/url directly or inside metadata_json)
    metadata = event_in.metadata_json or {}
    if event_in.title:
        metadata["title"] = event_in.title
    if event_in.url:
        metadata["url"] = event_in.url
    if event_in.description:
        metadata["description"] = event_in.description
        
    db_event = UserHistory(
        user_id=current_user.id,
        event_type=event_in.event_type,
        reference_id=event_in.reference_id,
        metadata_json=metadata
    )
    db.add(db_event)
    await db.commit()
    await db.refresh(db_event)
    
    return FrontendHistoryEvent(
        id=str(db_event.id),
        type=db_event.event_type,
        timestamp=db_event.created_at.isoformat(),
        title=metadata.get("title", "Activity"),
        description=metadata.get("description"),
        url=metadata.get("url")
    )
