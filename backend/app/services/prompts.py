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
    if paper.get("full_text_sample"):
        lines.append(f"\n--- FULL TEXT SNIPPETS ---\n{paper['full_text_sample']}\n--------------------------\n")
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

def build_qa_messages(paper: Dict[str, Any], question: str, history: Optional[List[Dict[str, str]]] = None, extra_context: str = "") -> List[Dict[str, str]]:
    context = _build_paper_context(paper, extra=extra_context)
    messages = [
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
        }
    ]
    if history:
        messages.extend(history)
        
    messages.append({
        "role": "user",
        "content": (
            f"--- PAPER CONTEXT ---\n{context}\n--- END CONTEXT ---\n\n"
            f"Question: {question}"
        ),
    })
    return messages


def build_project_qa_messages(project_context: str, question: str, history: Optional[List[Dict[str, str]]] = None) -> List[Dict[str, str]]:
    messages = [
        {
            "role": "system",
            "content": (
                "You are a research assistant that answers questions about a user's research project workspace. "
                "You MUST base your answer ONLY on the supplied project context. "
                "If the answer cannot be determined from the context, clearly state: "
                "'This information is not available in the provided context.' "
                "Do NOT hallucinate or invent facts. "
                "You must cite which papers support your claims based on the context. "
                "IMPORTANT: Do NOT output any <think>, <analysis>, <reasoning>, or <scratchpad> blocks. "
                "Do NOT show your chain of thought. "
                "Do NOT show your internal reasoning process. "
                "Respond with a plain text answer only — the direct, user-facing response. "
                "At the very end of your response, on its own line, write either "
                "'GROUNDED: true' if your answer was fully supported by the context, "
                "or 'GROUNDED: false' if you had to note unavailable information."
            ),
        }
    ]
    if history:
        messages.extend(history)
        
    messages.append({
        "role": "user",
        "content": (
            f"--- PROJECT CONTEXT ---\n{project_context}\n--- END CONTEXT ---\n\n"
            f"Question: {question}"
        ),
    })
    return messages


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
                "If information for a dimension is not available, write 'Not available' or '-'. "
                "Do NOT output any <think>, <reasoning>, or <scratchpad> blocks. "
                "\n"
                "Return valid JSON with EXACTLY these keys:\n"
                "{\n"
                "  \"dimensions\": [\n"
                "    {\n"
                "      \"name\": \"<dimension name, e.g. Problem, Methodology, Dataset, Results>\",\n"
                "      \"values\": [\"<value for paper 1>\", \"<value for paper 2>\", ...]\n"
                "    }\n"
                "  ],\n"
                "  \"overall_summary\": \"<1-2 paragraph summary of the comparison>\",\n"
                "  \"key_differences\": [\"<list of key differences>\"],\n"
                "  \"commonalities\": [\"<list of commonalities>\"],\n"
                "  \"research_takeaway\": \"<synthesis of trade-offs and directions>\"\n"
                "}\n"
                "Ensure the 'values' array in each dimension has exactly one entry per paper, in the same order as provided."
            ),
        },
        {
            "role": "user",
            "content": (
                f"{contexts}\n--- END CONTEXTS ---\n\n"
                "Compare these papers across dimensions such as Problem, Methodology, Dataset, Results, Limitations, and Future Work. "
                "Return as JSON with the specified structure."
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


# ── Concept Extraction ─────────────────────────────────────────────────────────

#: Closed relationship vocabulary for the concept graph. Keeping this fixed is
#: what stops the model inventing a new edge label per paper, which would make
#: the graph unqueryable and every edge type a sample size of one.
CONCEPT_RELATION_TYPES = [
    "USES",            # method/system uses a component or technique
    "PROPOSES",        # paper's contribution introduces this concept
    "EVALUATED_ON",    # evaluated on a dataset/benchmark
    "IMPROVES",        # outperforms / improves upon
    "BASED_ON",        # builds on prior method
    "PART_OF",         # component-of relationship
    "COMPARED_TO",     # explicitly compared against
    "MEASURED_BY",     # assessed with a metric
]


def build_concept_extraction_messages(paper: Dict[str, Any]) -> List[Dict[str, str]]:
    """Extract concepts AND concept-to-concept relations, both with evidence.

    Two things changed relative to the original prompt, both for correctness
    rather than style:

    1. Every concept must carry a verbatim `evidence` quote from the supplied
       text. That gives each node provenance, and it makes a hallucinated
       concept detectable — an invented term cannot be quoted from the source,
       so the caller can drop concepts whose evidence is not present.
    2. Relations are drawn from a closed vocabulary. Free-form edge labels
       produced a different vocabulary for every paper, which is why the graph
       could never be queried meaningfully.
    """
    context = _build_paper_context(paper)
    rel_list = ", ".join(CONCEPT_RELATION_TYPES)
    return [
        {
            "role": "system",
            "content": (
                "You are an expert academic research analyst building a knowledge graph. "
                "Work ONLY from the supplied paper context. Never use outside knowledge.\n\n"
                "Extract 5 to 15 specific, technically meaningful concepts (methods, "
                "architectures, datasets, tasks, metrics, systems). Reject generic words "
                "such as 'model', 'data', 'result', 'approach', 'paper', 'method', "
                "'experiment' when they stand alone.\n\n"
                "Then extract relationships BETWEEN those concepts, using ONLY these "
                f"relation types: {rel_list}.\n"
                "Only assert a relationship the text actually supports. Do NOT invent "
                "edges to make the graph look connected. Returning few or no relations "
                "is correct when the text does not state them.\n\n"
                "Return a JSON object with EXACTLY this structure:\n"
                "{\n"
                '  "concepts": [\n'
                '    {"name": "Self-Attention", "importance": 0.9, '
                '"evidence": "<short verbatim quote from the context>"}\n'
                "  ],\n"
                '  "relations": [\n'
                '    {"source": "Transformer", "target": "Self-Attention", '
                '"type": "USES", "evidence": "<short verbatim quote>"}\n'
                "  ]\n"
                "}\n\n"
                "Rules: 'name' is the concept as written in the paper, in singular form "
                "where natural. 'importance' is a float 0.0-1.0. 'evidence' must be a "
                "short quote copied verbatim from the supplied context. Every 'source' "
                "and 'target' MUST exactly match a 'name' in your concepts list. "
                "Do NOT output <think>, <analysis>, <reasoning> or <scratchpad> blocks."
            ),
        },
        {
            "role": "user",
            "content": (
                f"--- PAPER CONTEXT ---\n{context}\n--- END CONTEXT ---\n\n"
                "Extract concepts and their relationships. Return JSON only."
            ),
        },
    ]


# ── Project Chat (with structured citations) ───────────────────────────────────

def build_project_chat_messages(
    project_context: str,
    question: str,
    paper_index: Dict[str, Dict[str, Any]],
    history: Optional[List[Dict[str, str]]] = None,
) -> List[Dict[str, str]]:
    """
    Build messages for project-scoped chat that returns structured JSON
    with an answer and grounded citations.

    paper_index: dict of {paper_id: {"title": str, "year": int}} for citation resolution.
    """
    paper_index_str = "\n".join(
        f"  [{pid}]: {info.get('title', 'Unknown')} ({info.get('year', 'N/A')})"
        for pid, info in paper_index.items()
    )

    messages: List[Dict[str, str]] = [
        {
            "role": "system",
            "content": (
                "You are SAIRA, an expert research assistant with access to a researcher's project workspace. "
                "You MUST answer using ONLY the supplied project context. "
                "Do NOT hallucinate papers, findings, or citations. "
                "Do NOT use general knowledge not present in the context. "
                "If the context is insufficient, explicitly say so. "
                "Clearly distinguish paper content from user notes and highlights. "
                "\n\n"
                "You MUST return a valid JSON object with EXACTLY these keys:\n"
                "{\n"
                "  \"answer\": \"<your grounded answer in plain text>\",\n"
                "  \"citations\": [\n"
                "    {\"paper_id\": \"<exact UUID from context>\", \"title\": \"<paper title>\", \"year\": <year or null>, \"reason\": \"<brief reason this paper supports the answer>\"}\n"
                "  ],\n"
                "  \"grounded\": true\n"
                "}\n"
                "Set grounded to false if you could not find sufficient information and had to note unavailability. "
                "Only include papers in citations that directly support claims in your answer. "
                "Do NOT fabricate paper_ids — use only IDs from the paper index below. "
                "Do NOT output any <think>, <analysis>, <reasoning>, or <scratchpad> blocks. "
                "\n\nPaper index (for citation resolution):\n" + paper_index_str
            ),
        }
    ]

    if history:
        messages.extend(history)

    messages.append({
        "role": "user",
        "content": (
            f"--- PROJECT CONTEXT ---\n{project_context}\n--- END CONTEXT ---\n\n"
            f"Question: {question}\n\n"
            "Return your response as a JSON object with keys: answer, citations, grounded."
        ),
    })
    return messages


# ── Literature Review — Paper-Level Analysis ───────────────────────────────────

def build_paper_analysis_for_review_messages(paper: Dict[str, Any]) -> List[Dict[str, str]]:
    """
    Extract structured per-paper analysis for aggregation into a literature review.
    Returns JSON suitable for cross-paper synthesis.
    """
    context = _build_paper_context(paper)
    return [
        {
            "role": "system",
            "content": (
                "You are a research analyst extracting structured information from an academic paper "
                "for inclusion in a systematic literature review. "
                "Extract information ONLY from the supplied paper context. "
                "Do NOT hallucinate or invent information not present in the context. "
                "Return valid JSON with EXACTLY these keys:\n"
                "{\n"
                "  \"paper_id\": \"<paper_id from context>\",\n"
                "  \"title\": \"<paper title>\",\n"
                "  \"year\": <year or null>,\n"
                "  \"authors\": \"<authors string>\",\n"
                "  \"research_problem\": \"<the core research problem addressed>\",\n"
                "  \"methodology\": \"<brief description of methods used>\",\n"
                "  \"datasets\": [\"<dataset names>\"],\n"
                "  \"models\": [\"<model/architecture names>\"],\n"
                "  \"algorithms\": [\"<algorithm names>\"],\n"
                "  \"metrics\": [\"<evaluation metrics>\"],\n"
                "  \"key_findings\": [\"<main results and findings>\"],\n"
                "  \"limitations\": [\"<stated or implied limitations>\"],\n"
                "  \"future_work\": [\"<future directions suggested>\"],\n"
                "  \"contribution\": \"<main contribution in one sentence>\"\n"
                "}\n"
                "If a field has no information in the context, use null or an empty list."
            ),
        },
        {
            "role": "user",
            "content": (
                f"--- PAPER CONTEXT ---\n{context}\n--- END CONTEXT ---\n\n"
                f"Paper ID for this paper: {paper.get('id', 'unknown')}\n\n"
                "Extract structured analysis of this paper and return as JSON."
            ),
        },
    ]


# ── Literature Review — Cross-Paper Synthesis ──────────────────────────────────

def build_lit_review_synthesis_messages(
    paper_analyses: List[Dict[str, Any]],
    project_name: str,
) -> List[Dict[str, str]]:
    """
    Synthesize multiple paper-level analyses into a structured literature review.
    The output is a comprehensive JSON structure that can be rendered as a full review.
    """
    analyses_str = "\n\n".join(
        f"--- PAPER {i+1} (ID: {a.get('paper_id', 'unknown')}) ---\n"
        f"Title: {a.get('title', 'Unknown')}\n"
        f"Year: {a.get('year', 'N/A')}\n"
        f"Authors: {a.get('authors', 'N/A')}\n"
        f"Problem: {a.get('research_problem', 'N/A')}\n"
        f"Method: {a.get('methodology', 'N/A')}\n"
        f"Datasets: {', '.join(a.get('datasets') or []) or 'N/A'}\n"
        f"Models: {', '.join(a.get('models') or []) or 'N/A'}\n"
        f"Key Findings: {'; '.join(a.get('key_findings') or []) or 'N/A'}\n"
        f"Limitations: {'; '.join(a.get('limitations') or []) or 'N/A'}\n"
        f"Future Work: {'; '.join(a.get('future_work') or []) or 'N/A'}\n"
        f"Contribution: {a.get('contribution', 'N/A')}"
        for i, a in enumerate(paper_analyses)
    )

    n_papers = len(paper_analyses)
    return [
        {
            "role": "system",
            "content": (
                "You are an expert research synthesizer writing a structured academic literature review. "
                "You will receive structured analyses of multiple papers and must synthesize them "
                "into a coherent, thematic review. "
                "\n\n"
                "STRICT RULES:\n"
                "- Synthesize across papers; do NOT summarize each paper individually.\n"
                "- Use paper IDs (UUIDs) for citations, never invent IDs.\n"
                "- Do NOT hallucinate findings, datasets, or methods not in the analyses.\n"
                "- Identify genuine themes, trends, contradictions, and gaps.\n"
                "- Write the overview and theme summaries as flowing academic prose.\n"
                "- Do NOT output any <think>, <reasoning>, or <scratchpad> blocks.\n"
                "\n"
                "Return valid JSON with EXACTLY these keys:\n"
                "{\n"
                "  \"title\": \"<Literature Review title, e.g. 'A Survey of [topic]'>\",\n"
                "  \"overview\": \"<2-4 paragraph academic synthesis overview>\",\n"
                "  \"themes\": [\n"
                "    {\"title\": \"<theme name>\", \"summary\": \"<theme synthesis, 1-3 paragraphs>\", \"paper_ids\": [\"<uuid>\"]}\n"
                "  ],\n"
                "  \"methodological_trends\": [\"<trend description with paper references>\"],\n"
                "  \"datasets\": [\"<dataset name: used by paper IDs>\"],\n"
                "  \"models\": [\"<model/architecture name>\"],\n"
                "  \"key_findings\": [\"<cross-paper finding with paper references>\"],\n"
                "  \"contradictions\": [\"<contradiction between papers, with paper IDs>\"],\n"
                "  \"research_gaps\": [\"<gap identified, with supporting paper IDs>\"],\n"
                "  \"future_directions\": [\"<direction, with supporting paper IDs>\"],\n"
                "  \"references\": [\n"
                "    {\"paper_id\": \"<uuid>\", \"title\": \"<title>\", \"year\": <year or null>, \"authors\": \"<authors>\"}\n"
                "  ]\n"
                "}"
            ),
        },
        {
            "role": "user",
            "content": (
                f"Project: {project_name}\n"
                f"Number of papers: {n_papers}\n\n"
                f"--- PAPER ANALYSES ---\n{analyses_str}\n--- END ANALYSES ---\n\n"
                "Synthesize these papers into a structured academic literature review. "
                "Return as JSON with the specified structure."
            ),
        },
    ]


# ── Unified scoped RAG (Paper Chat + Project Chat) ─────────────────────────────

GROUNDING_SYSTEM_PROMPT = (
    "You are SAIRA, a research assistant answering questions about scientific "
    "papers.\n\n"
    "GROUNDING POLICY — follow exactly:\n"
    "1. Answer using ONLY the RETRIEVED EVIDENCE below. Do not use outside "
    "knowledge, even if you are confident it is correct.\n"
    "2. When the evidence supports an answer, give it directly and completely. "
    "Do NOT refuse or hedge when the evidence is sufficient.\n"
    "3. When the evidence is insufficient, say so explicitly and set "
    '"abstained" to true. Partial evidence: answer what is supported and state '
    "what is missing.\n"
    "4. Every factual claim must cite the evidence_id it came from.\n"
    "5. NEVER invent an evidence_id, page number, or paper. Cite only ids that "
    "appear in the RETRIEVED EVIDENCE.\n"
    "6. If the evidence contradicts your prior knowledge, follow the evidence.\n\n"
    "Return a JSON object with EXACTLY these keys:\n"
    "{\n"
    '  "answer": "<your answer in plain text>",\n'
    '  "citations": [{"evidence_id": "<exact id from the evidence>", '
    '"claim": "<the specific claim this supports>"}],\n'
    '  "grounded": true,\n'
    '  "abstained": false\n'
    "}\n"
    "Do NOT output <think>, <analysis>, <reasoning> or <scratchpad> blocks."
)


def build_scoped_rag_messages(
    question: str,
    evidence_block: str,
    scope_description: str,
    history: Optional[List[Dict[str, str]]] = None,
) -> List[Dict[str, str]]:
    """Assemble the final payload for a scoped RAG answer.

    The four parts the audit requires are kept in clearly separated,
    individually labelled sections — system instructions, allowed conversation
    history, retrieved evidence, user question — so that reading the logged
    payload is enough to tell what influenced an answer. Evidence is placed in
    the same user message as the question (not a prior turn) so it cannot be
    mistaken for conversation history on a later turn.
    """
    messages: List[Dict[str, str]] = [
        {"role": "system", "content": GROUNDING_SYSTEM_PROMPT}
    ]

    # Conversation history is passed verbatim and bounded by the caller. It is
    # never summarized into the system prompt, which is how facts from an
    # earlier answer used to re-enter as if they were evidence.
    if history:
        messages.extend(history)

    if evidence_block.strip():
        evidence_section = (
            "--- RETRIEVED EVIDENCE ---\n"
            f"{evidence_block}\n"
            "--- END RETRIEVED EVIDENCE ---"
        )
    else:
        evidence_section = (
            "--- RETRIEVED EVIDENCE ---\n"
            "(no evidence was retrieved for this question)\n"
            "--- END RETRIEVED EVIDENCE ---"
        )

    messages.append({
        "role": "user",
        "content": (
            f"SCOPE: {scope_description}\n\n"
            f"{evidence_section}\n\n"
            f"QUESTION: {question}\n\n"
            "Answer using only the evidence above. Return JSON only."
        ),
    })
    return messages


# ── LLM-Wiki / OKF knowledge compilation ──────────────────────────────────────

#: Sections of a compiled knowledge page, in the order they are rendered.
#: Each entry is (json_key, heading). The compiler and the Markdown renderer
#: both read this, so a page's structure is defined in exactly one place.
KNOWLEDGE_SECTIONS: List[tuple] = [
    ("abstract", "Abstract"),
    ("research_problem", "Research Problem"),
    ("key_contributions", "Key Contributions"),
    ("methodology", "Methodology"),
    ("dataset", "Dataset"),
    ("experiments", "Experiments"),
    ("results", "Results"),
    ("limitations", "Limitations"),
]


def build_knowledge_compilation_messages(
    paper: Dict[str, Any], source_blocks: str
) -> List[Dict[str, str]]:
    """Compile one paper's source text into a structured knowledge page.

    The output is the LLM-Wiki page for this paper, and it has to survive being
    quoted back to a user as fact — so every substantive field carries a
    verbatim `evidence` quote drawn from the supplied text. The caller locates
    each quote in the real source entries; anything it cannot find is marked
    unverified rather than presented as grounded. That is the whole
    anti-hallucination mechanism, and it only works if the model is told
    plainly that inventing a quote is detectable.

    Abstention is explicitly allowed. A paper whose PDF extraction produced no
    Methods section should return an empty `methodology`, not a plausible
    guess — an empty section is recoverable, a fabricated one is not.
    """
    context = _build_paper_context(paper)
    section_keys = ", ".join(k for k, _ in KNOWLEDGE_SECTIONS)
    return [
        {
            "role": "system",
            "content": (
                "You are compiling a research paper into a structured knowledge page "
                "for a research assistant's wiki.\n\n"
                "ABSOLUTE RULES:\n"
                "1. Work ONLY from the SOURCE TEXT provided. Never use outside "
                "knowledge about this paper, its authors, or its field.\n"
                "2. Every field you fill must carry an `evidence` value: a SHORT "
                "VERBATIM quote (10-40 words) copied exactly from the SOURCE TEXT. "
                "Quotes are checked against the source. A quote that does not appear "
                "in the text marks the whole field as unverified.\n"
                "3. If the SOURCE TEXT does not cover a field, return an empty string "
                "for its text and an empty string for its evidence. An empty section "
                "is correct and expected. Do NOT guess, infer, or fill a gap with "
                "typical practice in the field.\n"
                "4. Do not copy long passages. Summarize in your own words, and let "
                "the `evidence` quote carry the attribution.\n"
                "5. BE BRIEF. Each field's `text` is at most 35 words and each "
                "`evidence` quote at most 20 words. This is a reference card, not a "
                "paraphrase of the paper. An over-long reply is cut off before it can "
                "be parsed, which loses the entire compilation — brevity is a "
                "correctness requirement here, not a style preference.\n\n"
                f"Fields: {section_keys}.\n\n"
                "Also extract:\n"
                "- `concepts`: at most 8 specific technical concepts, descriptions at "
                "most 12 words. Reject generic words ('model', 'data', 'result', "
                "'method', 'approach') standing alone.\n"
                "- `methods`: at most 5 named techniques, architectures or algorithms "
                "actually used or proposed by this paper.\n"
                "- `topics`: at most 4 broad research areas this paper belongs to.\n\n"
                "Return ONLY valid JSON with this exact shape:\n"
                "{\n"
                '  "abstract":         {"text": "...", "evidence": "..."},\n'
                '  "research_problem": {"text": "...", "evidence": "..."},\n'
                '  "key_contributions":{"text": "...", "evidence": "..."},\n'
                '  "methodology":      {"text": "...", "evidence": "..."},\n'
                '  "dataset":          {"text": "...", "evidence": "..."},\n'
                '  "experiments":      {"text": "...", "evidence": "..."},\n'
                '  "results":          {"text": "...", "evidence": "..."},\n'
                '  "limitations":      {"text": "...", "evidence": "..."},\n'
                '  "concepts": [{"name": "...", "description": "...", "evidence": "..."}],\n'
                '  "methods":  [{"name": "...", "description": "...", "evidence": "..."}],\n'
                '  "topics":   ["..."]\n'
                "}"
            ),
        },
        {
            "role": "user",
            "content": (
                f"{context}\n\n"
                f"=== SOURCE TEXT ===\n{source_blocks}\n\n"
                "Compile the knowledge page as JSON. Remember: empty is better than "
                "invented, and every evidence quote must appear verbatim above."
            ),
        },
    ]
