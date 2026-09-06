"""
Static leakage audit.

Scans the backend source for patterns that would let an answer reach the model
without passing through retrieval: hardcoded facts, answer dictionaries, cached
LLM results, summaries injected into prompts, mutable module-level state, and
evaluation fixtures importable from production code.

This is a source audit, so it reports *candidates* for review, not proven
leaks. Each hit carries file and line so it can be checked by hand; nothing is
auto-classified as safe.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List

from evaluation.config.evaluation_config import BACKEND_ROOT, EVAL_ROOT


@dataclass
class Finding:
    category: str
    severity: str          # high | medium | low | info
    file: str
    line: int
    snippet: str
    note: str

    def to_dict(self) -> Dict[str, Any]:
        return self.__dict__.copy()


#: (category, regex, severity, note)
PATTERNS = [
    ("answer_cache", r"\b(lru_cache|cached_property|@cache\b)",
     "medium", "Caching decorator — verify it never caches an LLM answer keyed by question."),
    ("module_level_mutable_state", r"^_?[a-z_]+(_cache|_store|_memo|_results)\s*[:=]\s*(\{|\[)",
     "high", "Module-level mutable container — could persist answers across requests."),
    ("hardcoded_answer_dict", r"(answers|gold|expected)\s*[:=]\s*\{",
     "high", "Dictionary named like an answer key."),
    ("summary_injection", r"summary_(tldr|eli5|student|researcher)",
     "medium", "Stored summary referenced — confirm it is not injected as retrieval evidence."),
    ("eval_import_in_prod", r"^\s*(from|import)\s+evaluation",
     "high", "Production code importing the evaluation package."),
    ("fixture_reference", r"fixtures?/",
     "medium", "Fixture path referenced from backend code."),
    ("hardcoded_paper_id", r"[\"'][0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}[\"']",
     "medium", "Hardcoded UUID — acceptable in scripts/tests, not in request paths."),
    ("global_statement", r"^\s*global\s+\w+",
     "high", "Global mutation inside a function."),
    ("hardcoded_model_id", r"[\"'](llama\d|mixtral|gemma|gpt-4|claude-)[^\"']*[\"']",
     "medium", "Model ID outside the routing table."),
]

#: Files that legitimately contain scratch/manual-test material.
SCRATCH = re.compile(r"(^|[\\/])(tests?|test_|_probe|scratch|inspect_db|fix_alembic|write_ctx)")


def scan_backend(root: Path = BACKEND_ROOT) -> List[Finding]:
    findings: List[Finding] = []
    for path in sorted(root.rglob("*.py")):
        rel = path.relative_to(root.parent).as_posix()
        if any(part in path.parts for part in ("venv", ".venv", "__pycache__", "alembic")):
            continue
        is_scratch = bool(SCRATCH.search(rel))
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for i, line in enumerate(lines, start=1):
            if line.lstrip().startswith("#"):
                continue
            for category, pattern, severity, note in PATTERNS:
                if re.search(pattern, line, re.MULTILINE):
                    findings.append(Finding(
                        category=category,
                        severity=("info" if is_scratch else severity),
                        file=rel, line=i,
                        snippet=line.strip()[:200],
                        note=(note + (" [scratch/test file]" if is_scratch else "")),
                    ))
    return findings


def runtime_checks() -> List[Dict[str, Any]]:
    """Assertions about live configuration relevant to leakage."""
    import sys
    sys.path.insert(0, str(BACKEND_ROOT))
    from app.core.config import settings

    out = []

    def check(name, passed, detail):
        out.append({"check": name, "passed": bool(passed), "detail": detail})

    check("eval_mode_enabled", settings.SAIRA_EVAL_MODE,
          "SAIRA_EVAL_MODE gates history injection during evaluation.")
    check("payload_logging_enabled", settings.SAIRA_LOG_LLM_PAYLOAD,
          "Final LLM payload is logged for inspection.")
    check("history_bounded", settings.RAG_MAX_HISTORY_MESSAGES <= 10,
          f"RAG_MAX_HISTORY_MESSAGES={settings.RAG_MAX_HISTORY_MESSAGES}")
    check("context_bounded", settings.RAG_MAX_CONTEXT_CHARS <= 40000,
          f"RAG_MAX_CONTEXT_CHARS={settings.RAG_MAX_CONTEXT_CHARS}")

    # No answer cache should exist anywhere in the request path.
    try:
        from app.services import retrieval_service as rs
        module_state = [
            n for n in dir(rs)
            if not n.startswith("__") and isinstance(getattr(rs, n), (dict, list))
        ]
        check("no_module_level_containers_in_retrieval", not module_state,
              f"module-level containers: {module_state or 'none'}")
    except Exception as exc:
        check("no_module_level_containers_in_retrieval", False, f"import failed: {exc}")

    return out


def run_audit() -> Dict[str, Any]:
    findings = scan_backend()
    by_sev: Dict[str, int] = {}
    for f in findings:
        by_sev[f.severity] = by_sev.get(f.severity, 0) + 1
    return {
        "findings": [f.to_dict() for f in findings],
        "counts_by_severity": by_sev,
        "counts_by_category": {
            c: sum(1 for f in findings if f.category == c)
            for c in {f.category for f in findings}
        },
        "runtime_checks": runtime_checks(),
        "note": "Static pattern matches are candidates for manual review, "
                "not confirmed leaks.",
    }


if __name__ == "__main__":
    import json
    print(json.dumps(run_audit(), indent=2))
