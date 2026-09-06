"""
Central configuration for the SAIRA evaluation harness.

Everything the harness does is driven from here so a run can be reproduced by
recording this object alongside the results. Nothing in this file selects a
specific paper: the evaluation corpus is discovered at run time (see
`discovery/document_discovery.py`). Fixtures exist only for deterministic
regression tests, never for the causal evaluation.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List

# evaluation/ lives next to backend/; the harness imports the real application
# code rather than reimplementing any of it.
EVAL_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = EVAL_ROOT.parent
BACKEND_ROOT = REPO_ROOT / "backend"
REPORTS_DIR = EVAL_ROOT / "reports"
TRACES_DIR = REPORTS_DIR / "traces"
FIXTURES_DIR = EVAL_ROOT / "fixtures"


@dataclass
class EvaluationConfig:
    # -- Corpus discovery ------------------------------------------------------
    #: arXiv queries used to discover evaluation documents. Multiple distinct
    #: topics are used so the two document-switch papers are genuinely
    #: different works rather than two versions of the same result.
    discovery_queries: List[str] = field(default_factory=lambda: [
        "transformer neural machine translation attention",
        "convolutional neural network image classification benchmark",
    ])
    #: How many candidates to pull per query before picking one that ingests.
    discovery_candidates_per_query: int = 6
    #: Minimum extracted chunks for a document to be usable as an eval target.
    min_chunks_required: int = 8

    # -- Question generation ---------------------------------------------------
    facts_per_document: int = 8
    min_facts_required: int = 5

    # -- Retrieval -------------------------------------------------------------
    retrieval_k_values: List[int] = field(default_factory=lambda: [1, 3, 5, 10])
    retrieval_top_k: int = 10

    # -- Causal tests ----------------------------------------------------------
    #: Deterministic string substitutions used by the perturbed-context test.
    #: Each is applied only if the token is actually present in the evidence,
    #: so a perturbation is never claimed when nothing was changed.
    perturbations: List[Dict[str, str]] = field(default_factory=lambda: [
        {"from": "Adam", "to": "SGD"},
        {"from": "0.1", "to": "0.99"},
        {"from": "4000", "to": "123"},
        {"from": "BLEU", "to": "ROUGE"},
        {"from": "8", "to": "77"},
    ])

    # -- Execution -------------------------------------------------------------
    #: Bound total LLM calls so a run is affordable and repeatable.
    max_questions_per_document: int = 6
    request_delay_seconds: float = 0.4
    #: Set false to skip generation-heavy phases and evaluate retrieval only.
    run_generation_tests: bool = True

    # -- Output ----------------------------------------------------------------
    reports_dir: Path = REPORTS_DIR
    traces_dir: Path = TRACES_DIR
    run_id: str = ""

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["reports_dir"] = str(self.reports_dir)
        d["traces_dir"] = str(self.traces_dir)
        return d


def load_config(**overrides: Any) -> EvaluationConfig:
    cfg = EvaluationConfig()
    for key, value in overrides.items():
        if value is not None and hasattr(cfg, key):
            setattr(cfg, key, value)
    cfg.reports_dir.mkdir(parents=True, exist_ok=True)
    cfg.traces_dir.mkdir(parents=True, exist_ok=True)
    return cfg


# ── Failure taxonomy ──────────────────────────────────────────────────────────
# Kept as explicit constants so a result file can never contain an ad-hoc
# failure label, and so "everything failed" can't be collapsed into one bucket.

class RagFailure:
    RETRIEVAL_FAILURE = "RETRIEVAL_FAILURE"
    GENERATION_FAILURE = "GENERATION_FAILURE"
    GROUNDING_FAILURE = "GROUNDING_FAILURE"
    CITATION_FAILURE = "CITATION_FAILURE"
    CONTEXT_INFLUENCE_FAILURE = "CONTEXT_INFLUENCE_FAILURE"
    PRIOR_KNOWLEDGE_OR_LEAKAGE = "PRIOR_KNOWLEDGE_OR_LEAKAGE"
    CORRECT_ABSTENTION = "CORRECT_ABSTENTION"
    TEST_ARTIFACT = "TEST_ARTIFACT"
    PASS = "PASS"


class GraphFailure:
    EXTRACTION_FAILURE = "EXTRACTION_FAILURE"
    NORMALIZATION_FAILURE = "NORMALIZATION_FAILURE"
    RELATIONSHIP_FAILURE = "RELATIONSHIP_FAILURE"
    PROVENANCE_FAILURE = "PROVENANCE_FAILURE"
    DUPLICATION_FAILURE = "DUPLICATION_FAILURE"
    ISOLATION_FAILURE = "ISOLATION_FAILURE"
    PERSISTENCE_FAILURE = "PERSISTENCE_FAILURE"
    API_FAILURE = "API_FAILURE"
    FRONTEND_GRAPH_FAILURE = "FRONTEND_GRAPH_FAILURE"
    PASS = "PASS"
