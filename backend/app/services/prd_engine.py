"""
Personalized Research Delta (PRD) Engine.

Computes the incremental value of a candidate paper relative to a user's workspace.
Dimensions:
- Semantic Delta (using dense embeddings if available, fallback to basic text similarity/LLM)
- Methodological Delta (using set operations on extracted entities)
- Empirical/Dataset Delta (using set operations on extracted entities)
- Gap Resolution (NLI entailment using LLM against user notes)
"""

import json
import logging
import math
from typing import Any, Dict, List

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models.project import Project
from app.models.paper import Paper
from app.models.project_paper import ProjectPaper
from app.models.paper_analysis import PaperAnalysis
from app.schemas.ai import PRDResponse
from app.services.groq_service import groq_service, GroqServiceError
from app.core.config import settings

logger = logging.getLogger(__name__)

# Configurable Weights (alpha, beta, gamma, delta)
# In a real system, these would be learnable parameters.
PRD_WEIGHTS = {
    "semantic": 0.3,
    "method": 0.3,
    "dataset": 0.2,
    "gap": 0.2
}


async def _build_workspace_context(session: AsyncSession, project_id: Any) -> Dict[str, Any]:
    """Extract papers, analyses, notes, and gaps from a project."""
    stmt = (
        select(Project)
        .options(
            selectinload(Project.project_papers).selectinload(ProjectPaper.paper).selectinload(Paper.analysis),
            selectinload(Project.project_papers).selectinload(ProjectPaper.notes),
            selectinload(Project.project_papers).selectinload(ProjectPaper.highlights)
        )
        .where(Project.id == project_id)
    )
    project = await session.scalar(stmt)
    if not project:
        raise ValueError("Project not found.")

    workspace_methods = set()
    workspace_datasets = set()
    notes = []

    for pp in project.project_papers:
        if pp.paper and pp.paper.analysis:
            analysis = pp.paper.analysis
            if analysis.algorithms:
                workspace_methods.update(analysis.algorithms)
            if analysis.datasets:
                workspace_datasets.update(analysis.datasets)
        
        for note in pp.notes:
            notes.append(note.content)

    return {
        "methods": workspace_methods,
        "datasets": workspace_datasets,
        "notes": notes,
        "name": project.name,
    }


class PRDEngine:
    
    async def _compute_semantic_delta(self, candidate_paper: Paper, workspace_papers: List[Paper]) -> float:
        """
        Placeholder for Dense Embedding calculation.
        S_Delta = 1 - max(CosineSim(Embed(P), Embed(p)) for p in workspace)
        Returns a dummy 0.5 if no embedding model is configured.
        """
        return 0.5

    async def _compute_nli_entailment(self, candidate_claims: str, note: str) -> float:
        """
        Use the LLM to score entailment between candidate claims and a specific user note.
        """
        model = settings.GROQ_PRIMARY_MODEL
        messages = [
            {
                "role": "system",
                "content": (
                    "You are an NLI entailment scorer. Determine if the CANDIDATE PAPER CLAIMS "
                    "resolves or addresses the user's NOTE. Output a single float between 0.0 and 1.0 representing the degree of resolution. Output ONLY the float."
                )
            },
            {
                "role": "user",
                "content": f"NOTE: {note}\n\nCANDIDATE PAPER CLAIMS: {candidate_claims}"
            }
        ]
        try:
            response = await groq_service.chat_complete(model, messages)
            return float(response.strip())
        except Exception:
            return 0.0

    async def calculate_prd(self, session: AsyncSession, project_id: Any, paper: Paper) -> PRDResponse:
        """
        Calculates the Formal PRD using multidimensional computation.
        """
        workspace = await _build_workspace_context(session, project_id)
        
        # 1. Semantic Delta
        # (Assuming we pass a list of workspace papers. For simplicity in this demo, we use a fixed value)
        s_delta = 0.5 
        
        # We need the candidate paper's analysis to compute set differences.
        # If it doesn't exist, we assume 1.0 (completely new methods/datasets).
        m_delta = 1.0
        d_delta = 1.0
        candidate_claims = paper.abstract or paper.title
        
        if paper.analysis:
            candidate_methods = set(paper.analysis.algorithms or [])
            candidate_datasets = set(paper.analysis.datasets or [])
            
            # 2. Methodological Delta: 1 if Candidate introduces a method NOT in Workspace, else 0
            if candidate_methods and candidate_methods.issubset(workspace["methods"]):
                m_delta = 0.0
                
            # 3. Empirical Delta: 1 if Candidate introduces a dataset NOT in Workspace, else 0
            if candidate_datasets and candidate_datasets.issubset(workspace["datasets"]):
                d_delta = 0.0
        
        # 4. Gap Resolution (G_Delta)
        g_delta = 0.0
        if workspace["notes"]:
            entailments = []
            for note in workspace["notes"][:5]:  # Limit to top 5 notes for performance
                score = await self._compute_nli_entailment(candidate_claims, note)
                entailments.append(score)
            if entailments:
                g_delta = max(entailments)

        # Weighted combination
        prd_score = (
            PRD_WEIGHTS["semantic"] * s_delta +
            PRD_WEIGHTS["method"] * m_delta +
            PRD_WEIGHTS["dataset"] * d_delta +
            PRD_WEIGHTS["gap"] * g_delta
        )
        
        # Explanation (generate a quick explanation using LLM based on calculated deltas)
        explanation_prompt = [
            {
                "role": "system",
                "content": "You are a research assistant explaining why a paper is novel to a user based on calculated metric scores. Keep it to 2-3 sentences. No internal thoughts."
            },
            {
                "role": "user",
                "content": f"Scores: Semantic={s_delta}, Method={m_delta}, Dataset={d_delta}, GapResolution={g_delta}. Explain the novelty."
            }
        ]
        explanation = await groq_service.chat_complete(settings.GROQ_PRIMARY_MODEL, explanation_prompt)
        
        return PRDResponse(
            prd_score=prd_score,
            semantic_delta=s_delta,
            method_delta=m_delta,
            dataset_delta=d_delta,
            gap_resolution=g_delta,
            explanation=explanation.strip(),
            model=settings.GROQ_PRIMARY_MODEL
        )

prd_engine = PRDEngine()
