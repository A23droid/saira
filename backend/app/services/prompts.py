"""
Reusable prompt builders for each AI task.

Each builder returns a list of dicts suitable for the Groq chat API:
  [{"role": "system", "content": "..."}, {"role": "user", "content": "..."}]

All prompts instruct models to:
- Use only supplied evidence
- Not fabricate facts, citations, or paper-specific claims
- Clearly state when information is not available in the context
- Follow the requested output format precisely
"""

from typing import Any, Dict, List, Optional


# ── Context Builder ───────────────────────────────────────────────────────────

def _build_paper_context(paper: Dict[str, Any], extra: str = "") -> str:
    """Format a paper dict into a clean context block for the LLM."""
    lines = []
    if paper.get("title"):
        lines.append(f"Title: {paper['title']}")
    if paper.get("abstract"):
        lines.append(f"Abstract: {paper['abstract']}")
    if paper.get("publication_year"):
        lines.append(f"Year: {paper['publication_year']}")
    if paper.get("venue"):
        lines.append(f"Venue: {paper['venue']}")
    if paper.get("source"):
        lines.append(f"Source: {paper['source']}")
    if paper.get("doi"):
        lines.append(f"DOI: {paper['doi']}")
    if paper.get("arxiv_id"):
        lines.append(f"arXiv ID: {paper['arxiv_id']}")
    if paper.get("citation_count") is not None:
        lines.append(f"Citations: {paper['citation_count']}")
    if extra:
        lines.append(f"\nAdditional context:\n{extra}")
    return "\n".join(lines)


# ── Summary ────────────────────────────────────────────────────────────────────

def build_summary_messages(paper: Dict[str, Any]) -> List[Dict[str, str]]:
    context = _build_paper_context(paper)
    return [
        {
            "role": "system",
            "content": (
                "You are a research assistant that summarizes academic papers. "
                "You MUST use ONLY the information provided in the paper context below. "
                "Do NOT fabricate facts, citations, or claims not present in the context. "
                "If information for a field is not available, leave it as an empty list or null. "
                "Return your answer as valid JSON with exactly these keys: "
                "tldr (string), key_findings (list of strings), methodology (string), "
                "contributions (list of strings), limitations (list of strings)."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Summarize the following research paper.\n\n"
                f"--- PAPER CONTEXT ---\n{context}\n--- END CONTEXT ---\n\n"
                "Return a JSON object with: tldr, key_findings, methodology, contributions, limitations."
            ),
        },
    ]


# ── Q&A ────────────────────────────────────────────────────────────────────────

def build_qa_messages(paper: Dict[str, Any], question: str) -> List[Dict[str, str]]:
    context = _build_paper_context(paper)
    return [
        {
            "role": "system",
            "content": (
                "You are a research assistant that answers questions about academic papers. "
                "You MUST base your answer ONLY on the supplied paper context. "
                "If the answer cannot be determined from the context, clearly state: "
                "'This information is not available in the provided context.' "
                "Do NOT hallucinate or invent paper-specific facts. "
                "IMPORTANT: Do NOT output any <think>, <analysis>, <reasoning>, or <scratchpad> blocks. "
                "Do NOT show your chain of thought. "
                "Do NOT show your internal reasoning process. "
                "Respond with a plain text answer only — the direct, user-facing response. "
                "At the very end of your response, on its own line, write either "
                "'GROUNDED: true' if your answer was fully supported by the context, "
                "or 'GROUNDED: false' if you had to note unavailable information."
            ),
        },
        {
            "role": "user",
            "content": (
                f"--- PAPER CONTEXT ---\n{context}\n--- END CONTEXT ---\n\n"
                f"Question: {question}"
            ),
        },
    ]


# ── Research Gap ───────────────────────────────────────────────────────────────

def build_research_gap_messages(paper: Dict[str, Any]) -> List[Dict[str, str]]:
    context = _build_paper_context(paper)
    return [
        {
            "role": "system",
            "content": (
                "You are a research assistant that identifies research gaps in academic papers. "
                "Based ONLY on the supplied paper context, identify: "
                "1) observed limitations stated or implied by the paper, "
                "2) missing research areas not addressed, "
                "3) possible future directions. "
                "Do NOT speculate beyond what the context implies. "
                "Return plain text with clearly labeled sections."
            ),
        },
        {
            "role": "user",
            "content": (
                f"--- PAPER CONTEXT ---\n{context}\n--- END CONTEXT ---\n\n"
                "Identify the research gaps, limitations, and potential future directions "
                "based on this paper. Label each section clearly."
            ),
        },
    ]


# ── Comparison ─────────────────────────────────────────────────────────────────

def build_comparison_messages(papers: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    contexts = "\n\n".join(
        f"--- PAPER {i+1} ---\n{_build_paper_context(p)}" for i, p in enumerate(papers)
    )
    return [
        {
            "role": "system",
            "content": (
                "You are a research assistant that compares academic papers. "
                "Use ONLY the supplied paper contexts. "
                "Do NOT invent differences or similarities not evidenced in the context. "
                "Return a structured comparison covering: methodology, contributions, limitations, and scope."
            ),
        },
        {
            "role": "user",
            "content": (
                f"{contexts}\n--- END CONTEXTS ---\n\n"
                "Compare these papers across methodology, contributions, limitations, and scope."
            ),
        },
    ]


# ── Recommendations ────────────────────────────────────────────────────────────

def build_recommendation_messages(paper: Dict[str, Any]) -> List[Dict[str, str]]:
    context = _build_paper_context(paper)
    return [
        {
            "role": "system",
            "content": (
                "You are a research assistant that provides reading and research recommendations. "
                "Based ONLY on the supplied paper context, suggest related research directions. "
                "Do NOT fabricate paper titles, authors, or citations. "
                "Return a plain text response with specific research directions to explore."
            ),
        },
        {
            "role": "user",
            "content": (
                f"--- PAPER CONTEXT ---\n{context}\n--- END CONTEXT ---\n\n"
                "Based on this paper, what related research directions should a researcher explore?"
            ),
        },
    ]


# ── Extraction (GPT-OSS 120B) ──────────────────────────────────────────────────

def build_extraction_messages(paper: Dict[str, Any]) -> List[Dict[str, str]]:
    context = _build_paper_context(paper)
    return [
        {
            "role": "system",
            "content": (
                "You are a structured information extraction assistant for academic papers. "
                "Extract information ONLY from the supplied paper context. "
                "If a category has no information in the context, return an empty list for it. "
                "Do NOT hallucinate dataset names, model names, algorithms, or metrics. "
                "Return valid JSON with exactly these keys: "
                "datasets (list of strings), models (list of strings), "
                "algorithms (list of strings), metrics (list of strings), "
                "limitations (list of strings), future_work (list of strings)."
            ),
        },
        {
            "role": "user",
            "content": (
                f"--- PAPER CONTEXT ---\n{context}\n--- END CONTEXT ---\n\n"
                "Extract the following from this paper and return as JSON: "
                "datasets, models, algorithms, metrics, limitations, future_work."
            ),
        },
    ]
