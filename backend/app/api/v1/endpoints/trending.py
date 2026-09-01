from typing import Any
import random

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_current_user
from app.models.user import User
from app.models.paper import Paper
from app.schemas.trending import TrendingPaperResponse, TrendData

router = APIRouter()

@router.get("", response_model=list[TrendingPaperResponse])
async def get_trending(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    # To implement trending, we sort papers by citation_count in descending order.
    # In a real app, this might be a complex query combining recency and citation delta.
    stmt = select(Paper).order_by(Paper.citation_count.desc().nulls_last()).limit(10)
    result = await db.scalars(stmt)
    papers = result.all()
    
    response = []
    for paper in papers:
        # Mock trend data based on the paper's stats
        delta = random.randint(5, 50)
        score = round(random.uniform(8.0, 9.9), 1)
        reason = "Highly cited in the last week" if score > 9.0 else "Gaining traction"
        
        response.append(
            TrendingPaperResponse(
                paper=paper,
                entry=TrendData(
                    weeklyCitationDelta=delta,
                    trendScore=score,
                    reason=reason
                )
            )
        )
        
    return response
