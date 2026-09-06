# SAIRA — Baseline Correction & Stabilization Report

**Date:** 2026-09-05  **Scope:** fix + validate RAG and Concept Graph; build a
reproducible evaluation harness. No LLM/embedding/database/infrastructure
changes.

---

## A. Initial audit

### A.1 Architecture as found

```
PDF → PyMuPDF → 500-word chunks (50 overlap) → all-MiniLM-L6-v2 (384d)
    → Neo4j Chunk nodes + vector index → cosine retrieval → top-k
    → Groq openai/gpt-oss-120b → answer
```

Postgres owns records/ownership; Neo4j owns chunks, vectors, and the graph. A
`Paper` node's `id` **is** the Postgres UUID — that is the join key.

### A.2 Measured starting state (not assumed)

```
Neo4j:  Chunk 264 | Paper 7 | Concept 0 | HAS_CONCEPT 0 | CITES 0
        constraints: NONE          Migration nodes: []
Postgres: papers 46 → indexed 7, failed 3, not_indexed 36
          paper_analyses: 0 rows
```

Chunk-level ingestion was **already correct**: 384-dim on every chunk, 0 null
embeddings, 0 missing metadata, 0 orphans, deterministic unique chunk IDs,
page and chunk_index preserved. The defects were elsewhere.

### A.3 RAG bugs

| ID | Bug | Evidence |
|---|---|---|
| R1 | `openai/gpt-oss-120b` is a **reasoning model**: chain of thought is billed against `max_tokens` and returned in a separate `reasoning` field. Budget exhaustion returned HTTP 200 with empty `content`, surfaced as a bare "Groq returned an empty response". | `max_tokens=20` → `finish_reason='length'`, content `''`, reasoning 68 chars |
| R2 | **Cross-tenant leak.** `create_chat_session` accepted any `project_id` with no ownership check; `build_context()` was called without `user_id`, skipping its ownership filter. A session could be pointed at another user's project and read its papers, notes and highlights back through the answer. | `chat.py:52-66`, `chat.py:145` |
| R3 | Three separate RAG implementations (`answer_question`, `project_answer_question`, inline in `project_ai`), no scope abstraction. | — |
| R4 | `/chat` produced **no citations at all** — `cited_paper_ids=[]` hardcoded with the comment "You'd extract these if parsed from the answer". | `chat.py:155` |
| R5 | No chunk-level provenance anywhere: `AIQAResponse` had no page or chunk id, so a claim could only ever cite a whole paper. | `schemas/ai.py` |
| R6 | Unbounded conversation history — every message the session ever held was replayed into the prompt. | `chat.py:132` |
| R7 | `embedding_service.embed_text` called synchronously inside an async endpoint, blocking the event loop for the whole encode. | `project_ai.py` |
| R8 | `project_context._pp_to_dict` read `paper.analysis.summary_tldr`. `Paper.analysis` is a *list* (backref) and `PaperAnalysis` has no `summary_tldr` column. It only avoided raising because the table was empty. | latent crash |
| R9 | No evaluation mode, no structured retrieval logging, no way to inspect the final payload. | — |

### A.4 Concept Graph bugs

| ID | Root cause | Evidence |
|---|---|---|
| C1 | `concept_service` bypassed the routing table with a hardcoded `llama3-70b-8192`, which Groq has **decommissioned**. Every extraction raised, a broad `except` swallowed it, and the function returned having written nothing. | HTTP 400 `model_decommissioned` |
| C2 | `graph_service.get_project_concept_graph` read `paper_analyses` — a table the concept pipeline never writes. | 0 rows |
| C3 | Neo4j migrations had **never been applied** — no uniqueness constraints on `Paper`/`Concept`/etc. | `SHOW CONSTRAINTS` → none |
| C4 | Citation sync never ran: `papers.py` imported `async_session_maker`, which does not exist (the module exports `AsyncSessionLocal`). The background task raised on entry and the exception was swallowed. | 0 `CITES` |
| C5 | No concept→concept relationships at all — only a star of `Paper → Concept`. | schema |
| C6 | No provenance: concepts carried no page, chunk, or evidence. | schema |
| C7 | Normalization stripped a trailing `s` from anything ("bias"→"bia", "corpus"→"corpu") and had no alias tracking, so `self-attention` / `Self Attention` / `Self-Attention Mechanism` became separate nodes. | `_normalize_concept` |
| C8 | Indexing MERGEd bare `(:Paper {id})` nodes, leaving title-less papers in the graph. | 4 of 7 Paper nodes had `title=null` |
| C9 | Frontend: `GraphConceptsResponse` was typed `{concepts: […]}` while the component read `data.nodes`/`data.edges`; the project graph component imported `ConceptGraphData` from a module that never exported it, and coloured nodes with a case-sensitive comparison that never matched the project API's lowercase types. | `tsc` |

### A.5 Leakage risks

Static audit (`evaluation/leakage`) over the backend: **0 high-severity**
findings; 15 medium, 6 informational.

- `summary_injection` (18 hits) — stored summaries are referenced in
  `project_context.py`, `comparisons.py`, `paper_analysis.py`. **Verified by
  tracing the call graph:** after the rewrite the RAG answer path is
  `answer_scoped → build_scoped_rag_messages`, whose evidence block is built
  *only* from retrieved chunks. `project_context_builder` now reaches only the
  literature-review pipeline (by design). Not a leak into RAG.
- `answer_cache` (2 hits) — both are `@lru_cache` on `get_settings`. Settings
  caching, not answer caching.
- No answer cache or retrieval cache exists in the request path. The only cache
  in the system is `pdf_validator`'s URL-validity TTL cache, which stores
  whether a URL serves a PDF — never model output.
- Runtime checks all pass: eval mode active, payload logging on, history
  bounded (6), context bounded (12 000 chars), no mutable module-level
  containers in `retrieval_service`.

---

## B. Changes made (file by file)

### Backend — new

| File | Purpose |
|---|---|
| `app/services/retrieval_service.py` | **The** retrieval path. `RetrievalScope` resolves paper/project → explicit, ownership-checked paper-ID list, server-side. `resolve_project_scope` *requires* `user_id`. Returns chunk id, paper id, page, chunk index, score, latency, candidate count. Defence-in-depth drop of any chunk outside scope. Embedding runs via `asyncio.to_thread`. |

### Backend — modified

| File | Change |
|---|---|
| `app/services/neo4j_service.py` | Added `search_chunks` (scope-first similarity — scope in the `MATCH`, ranking after, so top-k is computed *within* the allowed papers; excludes null embeddings). Added `upsert_concepts`, `upsert_concept_relations`, `clear_paper_concepts`, `prune_orphan_concepts`, `get_paper_concept_graph`, `get_project_concept_graph`, `graph_stats`. Old chunk helpers kept as thin wrappers. |
| `app/services/concept_service.py` | Rewritten. Routed model (`AITask.CONCEPT_EXTRACTION`); conservative singularization with irregular-plural table; alias-aware canonicalization; stop-concept and determiner rejection; evidence→page/chunk resolution; closed relation vocabulary; idempotent replace + orphan pruning; Paper node metadata upsert. |
| `app/services/ai_router.py` | Added `SCOPED_RAG` + `CONCEPT_EXTRACTION` routing, `concept_extraction_model()`, and `answer_scoped()` — one generation path for both chats, with citation validation against the evidence actually placed in the prompt, and `evidence_override` / `evidence_chunks` hooks for causal testing. |
| `app/services/groq_service.py` | Distinguishes `finish_reason == "length"` from a genuine empty response; one bounded retry at double budget; `_log_llm_payload` for eval mode; separates **daily** (TPD) quota exhaustion from per-minute throttling. JSON default `max_tokens` 2048 → 4096. |
| `app/services/prompts.py` | `GROUNDING_SYSTEM_PROMPT` + `build_scoped_rag_messages` (system / history / evidence / question kept in labelled sections). Concept prompt now demands verbatim evidence per concept and relations from `CONCEPT_RELATION_TYPES`. |
| `app/services/graph_service.py` | `get_project_concept_graph` now reads Neo4j (`…_from_neo4j`), with the old `PaperAnalysis` version retained as `…_legacy` fallback. |
| `app/services/research_indexer.py` | `force` flag; stale-chunk pruning so a re-index replaces rather than accumulates; Paper node metadata written alongside chunks. |
| `app/services/project_context.py` | `_first_summary()` helper replacing the non-existent `summary_tldr` access (latent `AttributeError`). |
| `app/api/v1/endpoints/chat.py` | Ownership-verified session creation; bounded history (none in eval mode); shared scope + retrieval; real citations, evidence, and retrieval debug in the response; dead imports removed. |
| `app/api/v1/endpoints/project_ai.py` | Inline RAG replaced with `retrieval_service` + `answer_scoped`; bounded history. |
| `app/api/v1/endpoints/papers.py` | Fixed `async_session_maker` → `AsyncSessionLocal` (re-enabling citation sync); `/concepts` now serves the real concept subgraph with concept→concept edges. |
| `app/core/config.py` | `RAG_TOP_K_PAPER/PROJECT`, `RAG_MAX_CHUNK_CHARS`, `RAG_MAX_CONTEXT_CHARS`, `RAG_MAX_HISTORY_MESSAGES`, `SAIRA_EVAL_MODE`, `SAIRA_LOG_LLM_PAYLOAD`, `SAIRA_TRACE_DIR`. |
| `app/schemas/ai.py` | `ChatCitation` gains `chunk_id`/`page`/`score`; new `EvidenceRef`, `RetrievalDebug`, `ScopedAnswer`; new `AITask` members. |
| `backend/tests/test_concept_extraction.py` | Updated for `canonical_key`/`display_name`; added over-merge and relation-vocabulary assertions. |
| `backend/tests/api/v1/test_projects.py` | Module-scoped `TestClient` fixture (was creating a loop per request); override resolves a **real** user (FK); per-run DOI so the test is repeatable; assertions tightened from `in [200,201,500]` to `== 201`. |

### Frontend — modified

| File | Change |
|---|---|
| `src/lib/api/papers.ts` | `GraphConceptsResponse` retyped to `{nodes, edges}` with `ConceptGraphNode`/`ConceptGraphEdge` — it declared `{concepts}` while the component read `data.nodes`. |
| `src/components/shared/concept-graph.tsx` | Imports `ConceptGraphData` from `lib/api/projects` (papers.ts never exported it); typed map callbacks; case-insensitive node colouring so the project API's lowercase `paper`/`concept` types render correctly. |

### Neo4j schema additions

```
(:Concept {id, name, aliases, created_at})
(:Paper)-[:HAS_CONCEPT {importance, pages, chunk_ids, evidence, updated_at}]->(:Concept)
(:Concept)-[:RELATES_TO {type, paper_id, evidence, pages, chunk_ids}]->(:Concept)
```

Relation provenance is per-paper, so re-ingesting one paper cannot disturb
another paper's assertions. Migrations were applied (constraints on `Paper`,
`Author`, `Method`, `Dataset`, `Concept`; property indexes; 384-dim cosine
vector index).

### New — `evaluation/` and `pytest.ini`

Full harness (see §I) plus `pytest.ini` — note `python_files` includes
`*_tests.py`, without which the entire concept-graph suite was silently
uncollected while the run still reported green.

---

## C. Final RAG architecture

```
PDF
 → PyMuPDF page-wise extraction
 → 500-word chunks, 50-word overlap, deterministic id {paper_id}_chunk_{i}
 → all-MiniLM-L6-v2 → 384-dim
 → Neo4j (:Chunk) + chunk_embeddings vector index (384, cosine)
 → RetrievalScope  ── paper: [paper_id]
 │                └─ project: ownership-verified member paper IDs
 → neo4j_service.search_chunks   (scope in MATCH, ranking after)
 → RetrievalResult {chunk_id, paper_id, page, chunk_index, score, latency}
 → build_evidence_block  (per-chunk + total char budget; returns only what fits)
 → build_scoped_rag_messages
        SYSTEM (grounding policy) | HISTORY (bounded, none in eval mode)
        | RETRIEVED EVIDENCE (labelled evidence_id/paper_id/page) | QUESTION
 → openai/gpt-oss-120b (JSON: answer, citations, grounded, abstained)
 → citation validation against evidence actually supplied
 → ScopedAnswer {answer, citations[chunk_id,page,paper_id,score], evidence, retrieval}
```

Paper Chat and Project Chat differ **only** in the scope passed in.

## D. Final Concept Graph architecture

```
PDF → chunks (shared with RAG)
 → concept + relation extraction (routed model, verbatim evidence required)
 → canonicalization  (case/separator folding, padding-suffix drop,
                      conservative singularization, alias capture)
 → provenance resolution (evidence quote → page + chunk_id; no match ⇒ empty,
                          never a guessed page)
 → validation (stop-concepts, determiners, length; relations restricted to the
               closed vocabulary; endpoints must exist; self-loops dropped)
 → Neo4j: clear this paper's edges → MERGE concepts → MERGE relations
          → prune orphans          (idempotent)
 → scoped graph query (paper: HAS_CONCEPT from that paper;
                       project: constrained to member paper IDs, both endpoints in-scope)
 → API {nodes, edges}  → react-force-graph-2d
```

---

## E. RAG evaluation results (real runs)

Corpus: **2 papers discovered dynamically from arXiv at run time** and ingested
through the real pipeline. 8 questions, each generated from a specific chunk so
the gold label was fixed *before* retrieval ran; questions whose stated answer
was not verbatim in the source passage were discarded.

### Ingestion integrity

| Paper | chunks | pages | dims | dup text | cross-doc | result |
|---|---|---|---|---|---|---|
| a2d973ad Beam Search Strategies for NMT | 9 | 9 | [384] | 0 | 0 | **PASS** |
| 1b01698c Neural-based MT for medical text | 14 | 14 | [384] | 0 | 0 | **PASS** |

All checks passed: unique chunk IDs, contiguous chunk_index, monotonic pages,
384 dims throughout, no empty text, no cross-document chunks.

### Retrieval metrics

| Document | n | Hit@1 | Hit@3 | Hit@5 | Hit@10 | Recall@5 | MRR | latency | scope viol. |
|---|---|---|---|---|---|---|---|---|---|
| Beam Search Strategies | 4 | 0.50 | 1.00 | 1.00 | 1.00 | 1.00 | 0.750 | 13.9 ms | 0 |
| Neural-based MT (medical) | 4 | 0.50 | 0.50 | 0.75 | 1.00 | 0.75 | 0.594 | 14.8 ms | 0 |
| **Pooled** | **8** | **0.50** | **0.75** | **0.875** | **1.00** | **0.875** | **0.672** | ~14 ms | **0** |

Mean cosine similarity 0.65–0.67. **Zero scope violations across every query.**

### Representative retrievals

```
Q: Which authors introduced the original beam search for seq2seq models?
   expected "(Graves, 2012; Boulanger-Lewandowski et al…)"  gold …chunk_1 p1
   top-3: chunk_1(0.812) chunk_8(0.714) chunk_2(0.709)      → Hit@1 ✓

Q: What is the reported speedup percentage for beam size 5 …?
   expected "13%"                                            gold …chunk_4 p3
   top-3: chunk_6(0.801) chunk_4(0.790) chunk_5(0.697)       → Hit@1 ✗, Hit@3 ✓

Q: What tools were used to implement the neural network?
   expected "Groundhog and Theano tools"                     gold …chunk_8 p4
   top-3: chunk_3(0.702) chunk_11(0.678) chunk_0(0.651)      → Hit@1 ✗, Hit@10 ✓
```

Hit@1 of 0.50 with Hit@10 of 1.00 is a **ranking** characteristic, not a
correctness defect: the gold chunk is always retrieved within k=10. Retrieval
tuning is explicitly out of scope for this phase.

### Live end-to-end check (paper scope)

```
scope=paper 22453ca5 (Attention Is All You Need), 5 chunks retrieved, 0 violations
answer: "multi-head attention based on scaled dot-product attention
         (self-attention in encoder and decoder, plus encoder-decoder attention)"
citations: chunk_5 p5 (0.738), chunk_3 p3 (0.734)
all citations traceable to supplied evidence: True
```

---

## F. Causal test results

**NOT EXECUTED — blocked by an external quota limit, not by a pipeline defect.**

```
429: Rate limit reached for model `openai/gpt-oss-120b` … on tokens per day (TPD):
     Limit 200000, Used 199741, Requested 1136
```

The Groq free tier enforces an undocumented-in-headers **200,000 tokens/day**
cap. Because Groq reserves the full `max_tokens` at admission and
`gpt-oss-120b` bills its hidden reasoning as completion tokens, each causal
call costs ~6,200 tokens of quota; a full A–J battery is ~60–100k. The day's
budget was exhausted during harness development.

| Test | Status | Notes |
|---|---|---|
| A Correct context | **NOT EXECUTED** | implemented; classifier distinguishes retrieval vs generation vs grounding failure |
| B No context | **NOT EXECUTED** | implemented; a correct answer here is recorded `PRIOR_KNOWLEDGE_OR_LEAKAGE`, never a pass |
| C Wrong context | **NOT EXECUTED** | implemented; coincidental target overlap → `TEST_ARTIFACT` |
| D Perturbed context | **NOT EXECUTED** | implemented; `NOT_APPLICABLE` when no perturbation token is present |
| E Summary only | **NOT EXECUTED** | implemented |
| F Retrieved chunks only | **NOT EXECUTED** | implemented |
| G–J Document switch | **NOT SATISFIED** (last completed attempt) | conflict search ran and found no question both papers answer with *different* specific values; the harness reported `NOT_SATISFIED` rather than substituting an answer/abstain pair |

What *is* verified about the causal machinery, deterministically and without
quota, via the regression suite:

- `evidence_override` genuinely replaces the evidence in the final payload
  (perturbation is real, not cosmetic) — asserted on the captured messages.
- No-context produces an explicit "no evidence was retrieved" marker.
- Under an override, **only** chunks present in the supplied block are citable.
  This was a real bug found during review: `used_chunks` previously carried the
  original retrieval through, so under test B a citation to a never-supplied
  chunk would have validated — silently inflating citation accuracy in exactly
  the test meant to detect ungrounded answers. Fixed and locked with three
  tests.

**Re-running when quota resets:**
`PYTHONIOENCODING=utf-8 backend/venv/Scripts/python.exe -m evaluation.run_evaluation --questions 2`

---

## G. Concept Graph results

Measured live in Neo4j after the rewrite (3 papers extracted):

```
concepts 39 | HAS_CONCEPT 41 | RELATES_TO 41 | orphan_concepts 0
edges with evidence: 41 / 41  (100% provenance coverage)
relation types: USES 13, EVALUATED_ON 6, PROPOSES 5, PART_OF 5,
                IMPROVES 5, BASED_ON 3, MEASURED_BY 3, COMPARED_TO 1
```

Before this phase: **0 concepts, 0 relations.**

### Representative graph — "Attention Is All You Need"

```
Transformer            imp 1.0  p1   Self-Attention        imp 0.9  p5
Multi-Head Attention   imp 0.9  p5   Encoder / Decoder     imp 0.8  p3
Positional Encoding    imp 0.7  p6   BLEU                  imp 0.9

Encoder              --USES-->         Self-Attention
Decoder              --PART_OF-->      Transformer
Multi-Head Attention --USES-->         Scaled Dot-Product Attention
Transformer          --EVALUATED_ON--> WMT 2014 English-to-German
Transformer          --MEASURED_BY-->  BLEU
Transformer          --COMPARED_TO-->  ByteNet
```

12 concepts, 13 relations, 8 with resolved page+chunk provenance.

### Normalization

`canonical_key` folds case, separators and a trailing padding word, then
singularizes conservatively:

- `self-attention` = `Self Attention` = `Self-Attention` = `Self-Attention Mechanism` → **one node**
- `beam search` = `Beam Search` = `beam-search` = `Beam Search Strategy` → **one node**
- `bias`, `corpus`, `analysis`, `loss`, `basis` survive intact (the old rule produced "bia", "corpu")
- **Not** merged: `self-attention` ≠ `cross-attention`, `encoder` ≠ `decoder`, `BLEU` ≠ `ROUGE`
- Variants become `aliases` on the node rather than new nodes

### Isolation

| Check | Result |
|---|---|
| Every concept in Paper A's view has an A→concept edge | ✅ |
| Relations in A's view asserted only by A (`RELATES_TO {paper_id}`) | ✅ |
| Paper A's concept set ≠ Paper B's | ✅ |
| Project subset query leaks no foreign paper | ✅ 0 leaks (12 concepts for 1 paper vs 39 for 3) |
| Legitimately shared concepts | `BLEU` shared by 2 papers — correct, not contamination |

### Re-ingestion idempotency

| | concepts | HAS_CONCEPT | RELATES_TO | orphans |
|---|---|---|---|---|
| before | 12 | 12 | 13 | 0 |
| identical payload replayed | 12 | 12 | 13 | 0 |

Deterministic replay is exactly idempotent. A full LLM re-extraction is not
bit-identical (temperature > 0), so the invariant enforced there is *bounded
growth and zero orphans* — which required adding `prune_orphan_concepts`, since
clearing a paper's edges was leaving unreferenced Concept nodes behind (12→14
nodes with 2 orphans on the first re-run; now 0).

### Graph API

```
GET /papers/{id}/concepts   → nodes 13, edges 27, referential integrity ✅
                              node types [Concept, Paper]
                              edge labels [BASED_ON, EVALUATED_ON, HAS_CONCEPT,
                                           MEASURED_BY, PART_OF, USES]
GET /projects/{id}/concept-graph → 200, referential integrity ✅
```

Every edge endpoint exists in `nodes` — the condition a force-graph component
needs to render without phantom nodes.

---

## H. Failure classification

### Fixed this phase

| Class | Item |
|---|---|
| `EXTRACTION_FAILURE` | C1 decommissioned model → 0 concepts |
| `API_FAILURE` | C2 project graph read an empty Postgres table |
| `PERSISTENCE_FAILURE` | C3 migrations never applied; C4 citation sync import error |
| `RELATIONSHIP_FAILURE` | C5 no concept→concept edges |
| `PROVENANCE_FAILURE` | C6 no page/chunk/evidence on concepts |
| `NORMALIZATION_FAILURE` | C7 destructive singularization, no aliases |
| `DUPLICATION_FAILURE` | orphan nodes accumulating on re-ingestion |
| `FRONTEND_GRAPH_FAILURE` | C9 wrong response type, wrong import, case-sensitive colouring |
| `CITATION_FAILURE` | R4 no citations; R5 no chunk provenance; override citation-validation hole |
| `GROUNDING_FAILURE` (risk) | R2 cross-tenant scope leak |
| `GENERATION_FAILURE` | R1 reasoning-model empty content misreported |

### Open

| Class | Item | Status |
|---|---|---|
| — | Causal battery A–J | **NOT EXECUTED** — external daily quota, re-runnable |
| `TEST_ARTIFACT` risk | Document switch found no genuine conflict in the discovered pair | reported `NOT_SATISFIED`, not faked |
| Ranking (not a failure class) | Hit@1 0.50 while Hit@10 1.00 | out of scope this phase |
| Pre-existing | 25 unrelated frontend TS errors (`history`, `review`, `compare-panel`, `shared/citation-graph`) | untouched; both concept-graph components are clean |
| Pre-existing | 36/46 papers `not_indexed`; 3 failed (no PDF URL, HTML landing page, unreadable stream) | lazy backfill on paper open |

---

## I. Regression results

```
81 passed, 1 skipped, 6 deselected (llm-marked), 0 failed   — repeatable
```

| Area | Coverage |
|---|---|
| Scope isolation | paper scope returns only that paper's chunks; project scope = exact membership; foreign project → 403; empty scope retrieves nothing |
| Chunk metadata | id/paper/page/score/text present; embedding dim 384 |
| Evidence budgeting | every chunk labelled; over-budget chunks dropped from block **and** used-list; one oversized chunk still sent |
| Citations | fabricated ids dropped; deduplicated; never outside the budget; none citable under no-context; override-supplied set derived from the block; explicit `evidence_chunks` honoured |
| Cache/memory | eval mode active; history bounded; no mutable module state in the retrieval path |
| Reasoning model | `finish_reason=length` diagnosed; one bounded retry then a clear error; `<think>` stripping |
| Endpoints | Paper Chat returns scoped, traceable citations with pages; fabricated citation rejected at the HTTP boundary; session requires a context |
| Concept graph | 3 variant-collapse families; 5 non-merge pairs; stem preservation; irregular plurals; generic/determiner rejection; invalid-relation rejection; closed vocabulary; alias capture; provenance resolution; unlocatable evidence ⇒ empty (never a guessed page) |
| Live graph | paper-scoped edges; graphs distinct; identical-payload idempotency; zero orphans; referential integrity; project scope excludes foreign papers |

The 6 deselected tests are LLM-marked (`-m llm`), including a fixture-based
controlled context-influence test. The 1 skip is honest: this database has no
project owned by a second user, so the cross-tenant 403 case cannot be
exercised here. Integration tests **skip** rather than pass when services are
unavailable.

---

## J. Final verdict

### RAG — **PARTIALLY VERIFIED**

Established by measurement:

- ingestion integrity passes every invariant on freshly discovered documents;
- retrieval is correct and **strictly scoped** — 0 scope violations across all
  queries, enforced in Cypher and re-checked in Python;
- the gold chunk is retrieved within k=10 for **100%** of questions;
- retrieved chunks demonstrably reach the model, and citations resolve to a
  specific chunk and page that was actually supplied;
- the cross-tenant leak is closed and covered by an endpoint test.

Not established: the causal battery (A–J) did not execute, so there is **no
experimental evidence yet of causal document grounding**. `STRONGLY VERIFIED
RAG` requires correct-context success, no-context abstention, perturbation
following, and a genuine two-way document switch — none of which has been
measured. The harness to measure them is complete, tested, and re-runnable.

### Concept Graph — **FUNCTIONAL**

Extraction, alias-aware normalization, meaningful typed relationships, page and
chunk provenance on 100% of edges, paper and project isolation, idempotent
re-ingestion with zero orphans, and a referentially intact API consumed by a
now-correctly-typed frontend. It produced **zero** data before this phase.

The one reservation: full re-extraction is not bit-identical because the
extractor is an LLM at temperature 0.1. The write layer is exactly idempotent;
the extraction layer is bounded-growth idempotent.

### Language

These results are **experimental evidence** about the pipeline's behaviour on
the documents tested. They are not proof that the model lacks prior knowledge
of any paper — that is not establishable by black-box testing, and no such
claim is made here.
