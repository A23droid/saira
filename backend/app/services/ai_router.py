"""
AI Router — the single, central model-selection layer for SAIRA.

Architecture:
    Backend API endpoint
        ↓
    AI Router  ← this module
        ↓
    Groq Service  (sanitizes reasoning blocks before returning)
        ↓
    Groq API → correct model

The model routing table lives ONLY here. No other file should decide
which model handles which task.

Current routing table:
    SUMMARY       → GROQ_PRIMARY_MODEL   (openai/gpt-oss-120b by default)
    QA            → GROQ_PRIMARY_MODEL
    RESEARCH_GAP  → GROQ_PRIMARY_MODEL
    COMPARISON    → GROQ_PRIMARY_MODEL
    RECOMMENDATION→ GROQ_PRIMARY_MODEL
    DATASET       → GROQ_EXTRACTION_MODEL (openai/gpt-oss-120b by default)
    MODELS        → GROQ_EXTRACTION_MODEL
    ALGORITHMS    → GROQ_EXTRACTION_MODEL
    METRICS       → GROQ_EXTRACTION_MODEL
    LIMITATIONS   → GROQ_EXTRACTION_MODEL
    FUTURE_WORK   → GROQ_EXTRACTION_MODEL

Both model IDs are read from settings (.env) — never hardcoded here.
"""

import logging
from typing import Any, Dict, List

from app.core.config import settings
from app.schemas.ai import (
    AITask,
    AISummaryResponse,
    AIExtractionResponse,
    AIQAResponse,
)
from app.services.groq_service import groq_service, GroqServiceError
from app.services.prompts import (
    build_summary_messages,
    build_qa_messages,
    build_research_gap_messages,
    build_comparison_messages,
    build_recommendation_messages,
    build_extraction_messages,
)

logger = logging.getLogger(__name__)

# ── Model Routing Table ────────────────────────────────────────────────────────
# Single source of truth for task → model mapping.
# Model IDs come from settings (configured in .env).

def _get_routing_table() -> Dict[AITask, str]:
    return {
        # Primary model: conversational / analytical tasks
        AITask.SUMMARY:        settings.GROQ_PRIMARY_MODEL,
        AITask.QA:             settings.GROQ_PRIMARY_MODEL,
        AITask.RESEARCH_GAP:   settings.GROQ_PRIMARY_MODEL,
        AITask.COMPARISON:     settings.GROQ_PRIMARY_MODEL,
        AITask.RECOMMENDATION: settings.GROQ_PRIMARY_MODEL,
        # Extraction model: structured information extraction
        AITask.DATASET:        settings.GROQ_EXTRACTION_MODEL,
        AITask.MODELS:         settings.GROQ_EXTRACTION_MODEL,
        AITask.ALGORITHMS:     settings.GROQ_EXTRACTION_MODEL,
        AITask.METRICS:        settings.GROQ_EXTRACTION_MODEL,
        AITask.LIMITATIONS:    settings.GROQ_EXTRACTION_MODEL,
        AITask.FUTURE_WORK:    settings.GROQ_EXTRACTION_MODEL,
    }


def _model_for(task: AITask) -> str:
    """Return the Groq model identifier for a given task."""
    table = _get_routing_table()
    model = table.get(task)
    if not model:
        raise GroqServiceError(f"No model configured for task: {task}")
    return model


# ── AI Router ──────────────────────────────────────────────────────────────────

class AIRouter:
    """
    Routes AI tasks to the appropriate Groq model via the Groq service.
    Model selection is centralized in _get_routing_table().
    All responses include the model identifier actually used.
    """

    async def summarize(self, paper: Dict[str, Any]) -> AISummaryResponse:
        """Generate a structured summary using the primary model."""
        model = _model_for(AITask.SUMMARY)
        messages = build_summary_messages(paper)
        try:
            data = await groq_service.chat_complete_json(model, messages)
            return AISummaryResponse(
                tldr=data.get("tldr"),
                key_findings=data.get("key_findings") or [],
                methodology=data.get("methodology"),
                contributions=data.get("contributions") or [],
                limitations=data.get("limitations") or [],
                model=model,
            )
        except GroqServiceError:
            raise
        except Exception as exc:
            logger.error("Summarize failed: %s", exc)
            raise GroqServiceError(f"Summary generation failed: {exc}") from exc

    async def answer_question(self, paper: Dict[str, Any], question: str) -> AIQAResponse:
        """Answer a question about a paper using the primary model."""
        model = _model_for(AITask.QA)
        messages = build_qa_messages(paper, question)
        # groq_service.chat_complete already strips <think>/reasoning blocks
        raw = await groq_service.chat_complete(model, messages)
        # Parse the GROUNDED: true/false marker from the end of the cleaned response
        grounded = True
        answer = raw
        lines = raw.splitlines()
        if lines:
            last = lines[-1].strip()
            if last.upper().startswith("GROUNDED:"):
                grounded = "true" in last.lower()
                answer = "\n".join(lines[:-1]).strip()
        return AIQAResponse(answer=answer, grounded=grounded, model=model)

    async def research_gap(self, paper: Dict[str, Any]) -> str:
        """Identify research gaps using the primary model. Returns plain text."""
        model = _model_for(AITask.RESEARCH_GAP)
        messages = build_research_gap_messages(paper)
        return await groq_service.chat_complete(model, messages)

    async def compare(self, papers: List[Dict[str, Any]]) -> str:
        """Compare papers using the primary model. Returns plain text."""
        model = _model_for(AITask.COMPARISON)
        messages = build_comparison_messages(papers)
        return await groq_service.chat_complete(model, messages)

    async def recommend(self, paper: Dict[str, Any]) -> str:
        """Generate research recommendations using the primary model. Returns plain text."""
        model = _model_for(AITask.RECOMMENDATION)
        messages = build_recommendation_messages(paper)
        return await groq_service.chat_complete(model, messages)

    async def extract(self, paper: Dict[str, Any]) -> AIExtractionResponse:
        """Extract structured info using the extraction model."""
        model = _model_for(AITask.DATASET)  # All extraction tasks use same model
        messages = build_extraction_messages(paper)
        try:
            data = await groq_service.chat_complete_json(model, messages)
            return AIExtractionResponse(
                datasets=data.get("datasets") or [],
                models=data.get("models") or [],
                algorithms=data.get("algorithms") or [],
                metrics=data.get("metrics") or [],
                limitations=data.get("limitations") or [],
                future_work=data.get("future_work") or [],
            )
        except GroqServiceError:
            raise
        except Exception as exc:
            logger.error("Extract failed: %s", exc)
            raise GroqServiceError(f"Information extraction failed: {exc}") from exc


# Module-level singleton — imported by the AI endpoint
ai_router = AIRouter()
