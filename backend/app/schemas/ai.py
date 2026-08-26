"""
Pydantic schemas for SAIRA's AI layer.

These are the typed contracts between the API endpoints and the AI Router.
They are kept separate from paper schemas to maintain clear boundaries.
"""

from enum import Enum
from typing import List, Optional
from pydantic import BaseModel


# ── Task Enum ─────────────────────────────────────────────────────────────────

class AITask(str, Enum):
    # Llama / primary conversational-model tasks
    SUMMARY = "summary"
    QA = "qa"
    RESEARCH_GAP = "research_gap"
    COMPARISON = "comparison"
    RECOMMENDATION = "recommendation"
    # GPT-OSS / extraction-model tasks
    DATASET = "dataset"
    MODELS = "models"
    ALGORITHMS = "algorithms"
    METRICS = "metrics"
    LIMITATIONS = "limitations"
    FUTURE_WORK = "future_work"
    # Personalized Research Delta tasks
    PRD_METHOD = "prd_method"
    PRD_DATASET = "prd_dataset"
    PRD_GAP = "prd_gap"
    # Project-level AI tasks
    PROJECT_CHAT = "project_chat"
    LIT_REVIEW_PAPER = "lit_review_paper"
    LIT_REVIEW_SYNTHESIS = "lit_review_synthesis"


# ── Request Schemas ────────────────────────────────────────────────────────────

class AISummaryRequest(BaseModel):
    paper_id: str


class AIExtractionRequest(BaseModel):
    paper_id: str


class AIQARequest(BaseModel):
    paper_id: Optional[str] = None
    question: str


class PRDRequest(BaseModel):
    project_id: str
    paper_id: str


class ProjectChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None  # pass to continue existing conversation

class IndependentReviewRequest(BaseModel):
    paper_ids: list[str]


# ── Citation Schema ────────────────────────────────────────────────────────────

class ChatCitation(BaseModel):
    """A single paper citation extracted from a project chat response."""
    paper_id: str
    title: str
    year: Optional[int] = None
    reason: str  # Why this paper was cited


# ── Response Schemas ───────────────────────────────────────────────────────────

class AISummaryResponse(BaseModel):
    tldr: Optional[str] = None
    key_findings: List[str] = []
    methodology: Optional[str] = None
    contributions: List[str] = []
    limitations: List[str] = []
    # Groq model identifier that produced this response (e.g. "openai/gpt-oss-120b")
    model: Optional[str] = None


class AIExtractionResponse(BaseModel):
    datasets: List[str] = []
    models: List[str] = []
    algorithms: List[str] = []
    metrics: List[str] = []
    limitations: List[str] = []
    future_work: List[str] = []


class AIQAResponse(BaseModel):
    answer: str
    # True if the answer is based on supplied context; False if LLM flagged unavailability
    grounded: bool = True
    # Groq model identifier that produced this response (e.g. "openai/gpt-oss-120b")
    model: Optional[str] = None


class ProjectChatResponse(BaseModel):
    """Response from project-scoped chat with structured citations."""
    answer: str
    citations: List[ChatCitation] = []
    grounded: bool = True
    model: Optional[str] = None
    session_id: Optional[str] = None


class AIStatusResponse(BaseModel):
    configured: bool
    primary_model: str
    extraction_model: str
    message: str


class PRDResponse(BaseModel):
    prd_score: float
    semantic_delta: float
    method_delta: float
    dataset_delta: float
    gap_resolution: float
    explanation: str
    model: Optional[str] = None


# ── Literature Review Schemas ─────────────────────────────────────────────────

class LitReviewTheme(BaseModel):
    title: str
    summary: str
    paper_ids: List[str] = []


class LitReviewReference(BaseModel):
    paper_id: str
    title: str
    year: Optional[int] = None
    authors: Optional[str] = None


class LiteratureReviewContent(BaseModel):
    """Structured output of the literature review pipeline."""
    title: str
    overview: str
    themes: List[LitReviewTheme] = []
    methodological_trends: List[str] = []
    datasets: List[str] = []
    models: List[str] = []
    key_findings: List[str] = []
    contradictions: List[str] = []
    research_gaps: List[str] = []
    future_directions: List[str] = []
    references: List[LitReviewReference] = []


class LiteratureReviewResponse(BaseModel):
    """API response for a project literature review."""
    id: Optional[str] = None
    project_id: str
    content: LiteratureReviewContent
    paper_count: int
    is_stale: bool = False
    created_at: Optional[str] = None
    model: Optional[str] = None


# ── Comparison Schemas ────────────────────────────────────────────────────────

class ComparisonDimension(BaseModel):
    name: str
    values: List[str]


class ComparisonContent(BaseModel):
    """Structured output of the paper comparison pipeline."""
    dimensions: List[ComparisonDimension] = []
    overall_summary: str
    key_differences: List[str] = []
    commonalities: List[str] = []
    research_takeaway: str

