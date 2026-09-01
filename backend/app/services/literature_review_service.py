import asyncio
import logging
import uuid
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.literature_review import LiteratureReview
from app.schemas.ai import LiteratureReviewContent, LiteratureReviewResponse
from app.services.ai_router import ai_router
from app.services.groq_service import GroqServiceError
from app.services.project_context import project_context_builder, compute_paper_set_version

logger = logging.getLogger(__name__)
BATCH_SIZE = 10


class LiteratureReviewService:
    """Orchestrates the multi-stage literature review generation pipeline."""

    async def _analyze_papers_in_batches(self, paper_dicts: List[Dict]) -> List[Dict]:
        analyses = []
        for i in range(0, len(paper_dicts), BATCH_SIZE):
            batch = paper_dicts[i: i + BATCH_SIZE]
            logger.info("Analyzing batch %d/%d (%d papers)", i // BATCH_SIZE + 1,
                        (len(paper_dicts) + BATCH_SIZE - 1) // BATCH_SIZE, len(batch))
            tasks = [ai_router.analyze_paper_for_review(p) for p in batch]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for j, result in enumerate(results):
                if isinstance(result, Exception):
                    logger.error("Paper analysis failed for %s: %s", batch[j].get("id"), result)
                    analyses.append({
                        "paper_id": str(batch[j].get("id", "")),
                        "title": batch[j].get("title", "Unknown"),
                        "year": batch[j].get("year"),
                        "authors": batch[j].get("authors", "N/A"),
                        "research_problem": None, "methodology": None,
                        "datasets": [], "models": [], "algorithms": [],
                        "metrics": [], "key_findings": [], "limitations": [],
                        "future_work": [], "contribution": None,
                    })
                else:
                    analyses.append(result)
        return analyses

    async def get_cached_review(self, session, project_id, user_id, current_paper_ids) -> Optional[LiteratureReviewResponse]:
        stmt = select(LiteratureReview).where(
            LiteratureReview.project_id == project_id,
            LiteratureReview.user_id == user_id,
        )
        review = await session.scalar(stmt)
        if not review:
            return None
        current_version = compute_paper_set_version(current_paper_ids)
        is_stale = review.paper_set_version != current_version or review.paper_count != len(current_paper_ids)
        try:
            content = LiteratureReviewContent(**review.content)
        except Exception as exc:
            logger.error("Failed to parse cached review: %s", exc)
            return None
        return LiteratureReviewResponse(
            id=str(review.id), project_id=str(project_id), content=content,
            paper_count=review.paper_count, is_stale=is_stale,
            created_at=review.created_at.isoformat(),
        )

    async def generate(self, session, project_id, user_id, force_regenerate=False) -> LiteratureReviewResponse:
        project, paper_dicts = await project_context_builder.get_all_paper_dicts(session, project_id, user_id)
        if project is None:
            raise ValueError("Project not found or access denied.")
        if not paper_dicts:
            raise ValueError("This project has no papers. Add papers before generating a literature review.")

        paper_ids = [p["id"] for p in paper_dicts]
        current_version = compute_paper_set_version(paper_ids)

        if not force_regenerate:
            cached = await self.get_cached_review(session, project_id, user_id, paper_ids)
            if cached and not cached.is_stale:
                logger.info("Returning cached review for project %s", project_id)
                return cached

        logger.info("Generating lit review for project %s (%d papers)", project_id, len(paper_dicts))

        analyses = await self._analyze_papers_in_batches(paper_dicts)
        content = await ai_router.synthesize_literature_review(analyses, project.name)

        stmt = select(LiteratureReview).where(
            LiteratureReview.project_id == project_id,
            LiteratureReview.user_id == user_id,
        )
        existing = await session.scalar(stmt)
        content_dict = content.model_dump()

        if existing:
            existing.paper_set_version = current_version
            existing.paper_count = len(paper_dicts)
            existing.content = content_dict
        else:
            session.add(LiteratureReview(
                project_id=project_id, user_id=user_id,
                paper_set_version=current_version, paper_count=len(paper_dicts),
                content=content_dict,
            ))

        await session.commit()

        stmt = select(LiteratureReview).where(
            LiteratureReview.project_id == project_id,
            LiteratureReview.user_id == user_id,
        )
        saved = await session.scalar(stmt)

        return LiteratureReviewResponse(
            id=str(saved.id) if saved else None,
            project_id=str(project_id),
            content=content,
            paper_count=len(paper_dicts),
            is_stale=False,
            created_at=saved.created_at.isoformat() if saved else None,
        )

    async def invalidate(self, session, project_id, user_id) -> bool:
        stmt = select(LiteratureReview).where(
            LiteratureReview.project_id == project_id,
            LiteratureReview.user_id == user_id,
        )
        review = await session.scalar(stmt)
        if not review:
            return False
        await session.delete(review)
        await session.commit()
        return True


literature_review_service = LiteratureReviewService()
