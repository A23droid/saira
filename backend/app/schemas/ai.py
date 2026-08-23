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


# ── Request Schemas ────────────────────────────────────────────────────────────

class AISummaryRequest(BaseModel):
    paper_id: str


class AIExtractionRequest(BaseModel):
    paper_id: str


class AIQARequest(BaseModel):
    paper_id: str
    question: str


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


class AIStatusResponse(BaseModel):
    configured: bool
    primary_model: str
    extraction_model: str
    message: str
