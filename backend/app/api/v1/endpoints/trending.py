from typing import Any
import math
from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_current_user
from app.models.user import User
from app.models.paper import Paper
from app.schemas.trending import TrendingPaperResponse, TrendData

router = APIRouter()

CURRENT_YEAR = datetime.utcnow().year


def _compute_trend_score(paper: Paper) -> tuple[float, int, str]:
    """
    Deterministic trending score in [0, 10] based on:
      - Citation velocity  (citations / years since publication)  — weight 0.55
      - Log-scaled citation count                                 — weight 0.30
      - Reference count (proxy for influence breadth)            — weight 0.15

    Returns (score, weekly_delta_estimate, reason).
    """
    citations = paper.citation_count or 0
    references = paper.reference_count or 0
    pub_year = paper.publication_year or CURRENT_YEAR

    age_years = max(CURRENT_YEAR - pub_year, 1)

    # Citation velocity — normalise against a "good" paper (~500 cit/yr → 1.0)
    velocity = citations / age_years
    velocity_norm = min(velocity / 500.0, 1.0)

    # Log-scaled citation mass — normalise against 10 000 citations → 1.0
    citation_mass = math.log1p(citations) / math.log1p(10_000)
    citation_mass = min(citation_mass, 1.0)

    # Reference breadth — normalise against 300 references → 1.0
    ref_norm = min(references / 300.0, 1.0)

    raw = 0.55 * velocity_norm + 0.30 * citation_mass + 0.15 * ref_norm
    score = round(raw * 10, 1)

    # Weekly citation delta: rough estimate ≈ annual velocity / 52
    weekly_delta = max(1, round(velocity / 52))

    if score >= 8.5:
        reason = "Extremely high citation velocity"
    elif score >= 6.5:
        reason = "Highly cited — gaining momentum"
    elif score >= 4.0:
        reason = "Steadily gaining traction"
    else:
        reason = "Rising in the community"

    return score, weekly_delta, reason


@router.get("", response_model=list[TrendingPaperResponse])
async def get_trending(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    # Fetch top papers by citation count; trending score re-ranks by velocity.
    stmt = (
        select(Paper)
        .order_by(Paper.citation_count.desc().nulls_last())
        .limit(30)  # fetch more so velocity re-ranking can bubble up newer gems
    )
    result = await db.scalars(stmt)
    papers = result.all()

    scored = []
    for paper in papers:
        score, weekly_delta, reason = _compute_trend_score(paper)
        scored.append((score, weekly_delta, reason, paper))

    # Sort by trend score descending, take top 10
    scored.sort(key=lambda x: x[0], reverse=True)
    scored = scored[:10]

    return [
        TrendingPaperResponse(
            paper=paper,
            entry=TrendData(
                weeklyCitationDelta=weekly_delta,
                trendScore=score,
                reason=reason,
            ),
        )
        for score, weekly_delta, reason, paper in scored
    ]
