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
from typing import Any, Dict, List, Optional

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
    build_project_qa_messages,
    build_project_chat_messages,
    build_paper_analysis_for_review_messages,
    build_lit_review_synthesis_messages,
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
        # Project-level AI tasks
        AITask.PROJECT_CHAT:    settings.GROQ_PRIMARY_MODEL,
        AITask.LIT_REVIEW_PAPER: settings.GROQ_EXTRACTION_MODEL,
        AITask.LIT_REVIEW_SYNTHESIS: settings.GROQ_PRIMARY_MODEL,
        # Unified scoped RAG (Paper Chat + Project Chat)
        AITask.SCOPED_RAG:     settings.GROQ_PRIMARY_MODEL,
        # Knowledge-graph extraction. Previously the concept service bypassed
        # this table with a hardcoded `llama3-70b-8192`, which Groq
        # decommissioned — every extraction 400'd and the concept graph stayed
        # empty. Routing it here means it can never silently diverge again.
        AITask.CONCEPT_EXTRACTION: settings.GROQ_EXTRACTION_MODEL,
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


def concept_extraction_model() -> str:
    """Model used for concept-graph extraction. Exposed so `concept_service`
    reads the routing table instead of naming a model itself."""
    return _model_for(AITask.CONCEPT_EXTRACTION)


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

    async def answer_question(
        self,
        db: "AsyncSession",
        paper_id: str,
        question: str,
        history: Optional[List[Dict[str, str]]] = None,
    ) -> AIQAResponse:
        """Answer a question about one paper.

        Rewritten during the LLM-Wiki migration to go through the same scoped
        pipeline Paper Chat uses. It previously carried its own inline
        retrieval, its own context budget constants, and — the actual bug — no
        citation validation at all, so this endpoint could return claims
        attributed to evidence that was never supplied. There is now exactly
        one retrieval path and one grounding policy in the codebase.

        The response schema is unchanged; `AIQAResponse` never exposed
        citations, so the extra structure `answer_scoped` produces is simply
        not surfaced here.
        """
        from app.services.retrieval_service import ScopeError, retrieval_service

        try:
            scope = await retrieval_service.resolve_paper_scope(db, paper_id)
        except ScopeError as exc:
            raise GroqServiceError(exc.detail) from exc

        retrieval = await retrieval_service.retrieve(db, scope, question)
        scoped = await answer_scoped(
            scope=scope, question=question, retrieval=retrieval, history=history,
        )
        return AIQAResponse(
            answer=scoped.answer, grounded=scoped.grounded, model=scoped.model,
        )

    async def research_gap(self, paper: Dict[str, Any]) -> str:
        """Identify research gaps using the primary model. Returns plain text."""
        model = _model_for(AITask.RESEARCH_GAP)
        messages = build_research_gap_messages(paper)
        return await groq_service.chat_complete(model, messages)

    async def compare(self, papers: List[Dict[str, Any]]) -> "ComparisonContent":
        """Compare papers using the primary model. Returns structured ComparisonContent."""
        from app.schemas.ai import ComparisonContent, ComparisonDimension
        model = _model_for(AITask.COMPARISON)
        messages = build_comparison_messages(papers)
        try:
            data = await groq_service.chat_complete_json(model, messages, max_tokens=4096)
        except GroqServiceError:
            raise
        except Exception as exc:
            raise GroqServiceError(f"Comparison failed: {exc}") from exc
        
        dimensions = [
            ComparisonDimension(
                name=d.get("name", "Unknown"),
                values=d.get("values") or []
            )
            for d in (data.get("dimensions") or [])
        ]

        return ComparisonContent(
            dimensions=dimensions,
            overall_summary=data.get("overall_summary") or "",
            key_differences=data.get("key_differences") or [],
            commonalities=data.get("commonalities") or [],
            research_takeaway=data.get("research_takeaway") or ""
        )

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

    async def project_chat(
        self,
        project_context: str,
        question: str,
        paper_index: Dict[str, Dict[str, Any]],
        history: Optional[List[Dict[str, str]]] = None,
    ) -> "ProjectChatResponse":
        """Answer a project-scoped question with grounded citations."""
        from app.schemas.ai import ProjectChatResponse, ChatCitation
        model = _model_for(AITask.PROJECT_CHAT)
        messages = build_project_chat_messages(project_context, question, paper_index, history)
        try:
            data = await groq_service.chat_complete_json(model, messages)
        except GroqServiceError:
            raise
        except Exception as exc:
            raise GroqServiceError(f"Project chat failed: {exc}") from exc

        answer = data.get("answer", "")
        grounded = bool(data.get("grounded", True))
        raw_citations = data.get("citations") or []

        # Validate citations — only keep those whose paper_id is in the actual paper index
        citations = []
        for c in raw_citations:
            pid = str(c.get("paper_id", ""))
            if pid and pid in paper_index:
                citations.append(ChatCitation(
                    paper_id=pid,
                    title=c.get("title") or paper_index[pid].get("title", "Unknown"),
                    year=c.get("year") or paper_index[pid].get("year"),
                    reason=c.get("reason", ""),
                ))

        return ProjectChatResponse(
            answer=answer,
            citations=citations,
            grounded=grounded,
            model=model,
        )

    async def analyze_paper_for_review(self, paper: Dict[str, Any]) -> Dict[str, Any]:
        """Extract structured paper-level analysis for literature review pipeline."""
        model = _model_for(AITask.LIT_REVIEW_PAPER)
        messages = build_paper_analysis_for_review_messages(paper)
        try:
            data = await groq_service.chat_complete_json(model, messages)
            # Ensure paper_id is the real DB ID, not whatever the model returned
            data["paper_id"] = str(paper.get("id", ""))
            data["title"] = data.get("title") or paper.get("title", "Unknown")
            data["year"] = data.get("year") or paper.get("year")
            data["authors"] = data.get("authors") or paper.get("authors", "N/A")
            return data
        except GroqServiceError:
            raise
        except Exception as exc:
            logger.error("Paper analysis failed for %s: %s", paper.get("id"), exc)
            # Return minimal fallback so the pipeline can continue with other papers
            return {
                "paper_id": str(paper.get("id", "")),
                "title": paper.get("title", "Unknown"),
                "year": paper.get("year"),
                "authors": paper.get("authors", "N/A"),
                "research_problem": None,
                "methodology": None,
                "datasets": [],
                "models": [],
                "algorithms": [],
                "metrics": [],
                "key_findings": [],
                "limitations": [],
                "future_work": [],
                "contribution": None,
            }

    async def synthesize_literature_review(
        self,
        paper_analyses: List[Dict[str, Any]],
        project_name: str,
    ) -> "LiteratureReviewContent":
        """Synthesize paper analyses into a full structured literature review."""
        from app.schemas.ai import LiteratureReviewContent, LitReviewTheme, LitReviewReference
        model = _model_for(AITask.LIT_REVIEW_SYNTHESIS)
        messages = build_lit_review_synthesis_messages(paper_analyses, project_name)
        try:
            data = await groq_service.chat_complete_json(model, messages, max_tokens=4096)
        except GroqServiceError:
            raise
        except Exception as exc:
            raise GroqServiceError(f"Literature review synthesis failed: {exc}") from exc

        # Parse themes
        themes = [
            LitReviewTheme(
                title=t.get("title", ""),
                summary=t.get("summary", ""),
                paper_ids=t.get("paper_ids") or [],
            )
            for t in (data.get("themes") or [])
        ]

        # Parse references
        references = [
            LitReviewReference(
                paper_id=r.get("paper_id", ""),
                title=r.get("title", ""),
                year=r.get("year"),
                authors=r.get("authors"),
            )
            for r in (data.get("references") or [])
        ]

        return LiteratureReviewContent(
            title=data.get("title") or f"Literature Review: {project_name}",
            overview=data.get("overview") or "",
            themes=themes,
            methodological_trends=data.get("methodological_trends") or [],
            datasets=data.get("datasets") or [],
            models=data.get("models") or [],
            key_findings=data.get("key_findings") or [],
            contradictions=data.get("contradictions") or [],
            research_gaps=data.get("research_gaps") or [],
            future_directions=data.get("future_directions") or [],
            references=references,
        )


# Module-level singleton — imported by the AI endpoint
ai_router = AIRouter()


# ── Unified scoped RAG ─────────────────────────────────────────────────────────

async def answer_scoped(
    scope: "RetrievalScope",
    question: str,
    retrieval: "RetrievalResult",
    history: Optional[List[Dict[str, str]]] = None,
    include_evidence_text: bool = False,
    evidence_override: Optional[str] = None,
    evidence_chunks: Optional[List["RetrievedChunk"]] = None,
) -> "ScopedAnswer":
    """Generate a grounded, cited answer from already-retrieved evidence.

    Paper Chat and Project Chat both land here; the only difference between
    them is the `scope` that produced `retrieval`. Keeping generation separate
    from retrieval is also what makes the causal evaluation possible — the
    harness can hand this function deliberately wrong or perturbed evidence
    via `evidence_override` and observe whether the answer follows it.

    Citations are resolved against the evidence actually sent to the model, so
    an `evidence_id` the model invents is dropped rather than returned. A
    citation therefore always points at a real chunk on a real page.
    """
    import json
    import re
    import time

    from app.schemas.ai import (
        ChatCitation, EvidenceRef, RetrievalDebug, ScopedAnswer,
    )
    from app.services.prompts import build_scoped_rag_messages
    from app.services.retrieval_service import retrieval_service

    model = _model_for(AITask.SCOPED_RAG)

    # Bound history centrally so no caller can pass an unbounded transcript.
    if history and len(history) > settings.RAG_MAX_HISTORY_MESSAGES:
        history = history[-settings.RAG_MAX_HISTORY_MESSAGES:]

    if evidence_override is not None:
        # Evaluation path: caller supplies the evidence block verbatim.
        evidence_block = evidence_override
        if evidence_chunks is not None:
            used_chunks = list(evidence_chunks)
        else:
            # Derive the supplied set from the block itself. Carrying the
            # original retrieval over would be wrong: under the no-context test
            # the block is empty, yet a citation to a chunk the model never saw
            # would still validate — exactly the failure the validator exists
            # to catch.
            supplied_ids = set(re.findall(r"evidence_id=([^\s|\]]+)", evidence_block))
            used_chunks = [c for c in retrieval.chunks if c.chunk_id in supplied_ids]
    else:
        evidence_block, used_chunks = retrieval_service.build_evidence_block(retrieval)

    scope_description = (
        f"{scope.type} '{scope.label}' "
        f"({len(scope.paper_ids)} paper(s) in scope)"
    )
    messages = build_scoped_rag_messages(
        question=question,
        evidence_block=evidence_block,
        scope_description=scope_description,
        history=history,
    )
    prompt_chars = sum(len(m.get("content", "")) for m in messages)

    started = time.perf_counter()
    try:
        data = await groq_service.chat_complete_json(model, messages, max_tokens=4096)
    except GroqServiceError:
        raise
    except Exception as exc:
        raise GroqServiceError(f"Scoped RAG generation failed: {exc}") from exc
    latency_ms = (time.perf_counter() - started) * 1000.0

    answer = str(data.get("answer") or "").strip()
    grounded = bool(data.get("grounded", True))
    abstained = bool(data.get("abstained", False))

    # -- Citation validation ---------------------------------------------------
    # Only evidence that was actually placed in the prompt may be cited.
    by_id = {c.chunk_id: c for c in used_chunks}
    citations: List[ChatCitation] = []
    seen: set[str] = set()
    for raw in (data.get("citations") or []):
        if not isinstance(raw, dict):
            continue
        ev_id = str(raw.get("evidence_id") or "").strip()
        chunk = by_id.get(ev_id)
        if chunk is None:
            logger.warning(
                "Dropped fabricated citation %r (not in supplied evidence for scope %s)",
                ev_id, scope.scope_id,
            )
            continue
        if ev_id in seen:
            continue
        seen.add(ev_id)
        citations.append(ChatCitation(
            paper_id=chunk.paper_id,
            title=chunk.paper_title or "",
            year=None,
            reason=str(raw.get("claim") or "")[:500],
            chunk_id=chunk.chunk_id,
            page=chunk.page,
            score=round(chunk.score, 6),
        ))

    evidence = [
        EvidenceRef(
            chunk_id=c.chunk_id,
            paper_id=c.paper_id,
            page=c.page,
            chunk_index=c.chunk_index,
            score=round(c.score, 6),
            paper_title=c.paper_title,
            text=(c.text if include_evidence_text else None),
        )
        for c in used_chunks
    ]

    debug = RetrievalDebug(
        scope_type=scope.type,
        scope_id=scope.scope_id,
        paper_ids=list(scope.paper_ids),
        candidate_count=retrieval.candidate_count,
        retrieved_chunk_ids=[c.chunk_id for c in used_chunks],
        similarity_scores=[round(c.score, 6) for c in used_chunks],
        retrieval_latency_ms=round(retrieval.latency_ms, 2),
        embedding_dim=retrieval.embedding_dim,
        error=retrieval.error,
    )

    return ScopedAnswer(
        answer=answer,
        grounded=grounded,
        abstained=abstained,
        citations=citations,
        evidence=evidence,
        model=model,
        retrieval=debug,
        prompt_chars=prompt_chars,
        generation_latency_ms=round(latency_ms, 2),
    )


# Attach to the router instance so callers can use either entry point.
AIRouter.answer_scoped = staticmethod(answer_scoped)
