# SAIRA Evaluation Harness

Reproducible evaluation for SAIRA's **RAG pipeline** and **Concept Graph**.

Everything here runs against the real application code in `backend/app`. The
harness never reimplements retrieval, generation, or extraction — it imports
the same services the API uses, so a passing result says something about the
product rather than about the harness.

**No result in this directory is hardcoded.** Every number in a report is
computed from the run that produced it, and every run writes a JSONL trace of
the steps behind those numbers.

---

## 1. Prerequisites

| Requirement | Why |
|---|---|
| PostgreSQL running, migrations applied | paper/project records |
| Neo4j 5+ running, `python app/db/run_migrations.py` applied | chunks, vectors, concept graph |
| `GROQ_API_KEY` set in `backend/.env` | generation + extraction |
| Backend venv with `requirements.txt` + `pytest` | the harness imports `app.*` |
| Outbound HTTPS to `arxiv.org` | dynamic document discovery |

The harness loads `backend/.env` itself, so it can be run from the repository
root without activating anything.

```bash
cd <repo root>
backend/venv/Scripts/python.exe -m pip install pytest        # once
```

---

## 2. Running

```bash
# Full evaluation: discovery → ingestion → retrieval → causal → graph
python -m evaluation.run_evaluation

# Cheap: retrieval metrics only, no generation-heavy causal tests
python -m evaluation.run_evaluation --retrieval-only

# Skip the concept-graph phase
python -m evaluation.run_evaluation --skip-graph

# Control cost (questions generated per document; default 6)
python -m evaluation.run_evaluation --questions 4
```

On Windows use the venv interpreter directly and force UTF-8 so model output
containing non-CP1252 characters does not crash the console:

```bash
PYTHONIOENCODING=utf-8 backend/venv/Scripts/python.exe -m evaluation.run_evaluation
```

### Regression tests

```bash
pytest evaluation/regression evaluation/concept_graph/graph_integrity_tests.py -v
```

Tests needing live services **skip** rather than fail when those services are
down, so a green run with skips is never mistaken for full verification — the
skip reason states this explicitly.

---

## 3. Output

```
evaluation/reports/
├── LATEST.md                      most recent run, human readable
├── <run_id>-report.md             per-run Markdown report
├── <run_id>-results.json          every measurement, machine readable
└── traces/<run_id>-trace.jsonl    per-step trace of the run
```

The trace holds one record per observable step — question generation,
retrieval, each causal test, each graph write — so any reported number can be
traced back to the call that produced it.

---

## 4. Layout

```
evaluation/
├── run_evaluation.py          orchestrator (7 phases)
├── reports_builder.py         results dict → Markdown (formatting only)
├── config/
│   └── evaluation_config.py   all knobs + the failure taxonomies
├── common/
│   ├── bootstrap.py           eval mode, .env loading, traces, loop isolation
│   └── reporting.py           JSON/Markdown writers
├── discovery/
│   └── document_discovery.py  dynamic arXiv corpus selection
├── ingestion/
│   └── evaluation_ingestion.py real-pipeline ingest + integrity verification
├── retrieval/
│   ├── retrieval_evaluation.py question generation + scoped retrieval runs
│   └── retrieval_metrics.py    Hit@k, Recall@k, MRR, precision, latency
├── grounding/
│   ├── causal_tests.py        tests A–F
│   ├── context_tests.py       tests G–J (conflicting document switch)
│   └── grounding_metrics.py   groundedness, citations, verdicts
├── leakage/
│   └── leakage_checks.py      static source audit + runtime config checks
├── concept_graph/
│   ├── graph_evaluation.py    extraction, isolation, idempotency, API
│   ├── graph_metrics.py       counts, provenance, classification, verdict
│   └── graph_integrity_tests.py  pytest invariants 14–21
├── regression/
│   └── test_rag_invariants.py    pytest invariants 1–13
├── reports/
└── fixtures/
```

---

## 5. Evaluation mode

`bootstrap()` sets `SAIRA_EVAL_MODE=true` and `SAIRA_LOG_LLM_PAYLOAD=true`
**before** `app.core.config` is imported (settings are `lru_cache`d, so order
matters). Evaluation mode:

- disables conversation-history injection in both chat endpoints,
- logs the exact final message array immediately before each model call,
- leaves retrieval scope, ranking, model choice, and prompts **unchanged**.

It reduces what can influence an answer; it never makes the system look better.
Production conversation functionality is untouched — it is gated, not removed.

There is no answer cache or retrieval cache in the request path. The only cache
in the system is `pdf_validator`'s URL-validity TTL cache, which stores whether
a URL serves a PDF — never model output. A regression test asserts the
retrieval module holds no mutable module-level state.

---

## 6. What the causal tests mean

A correct answer is **not** evidence that RAG works — the model may already
know the paper. Each test therefore manipulates the evidence and checks whether
the answer follows it.

| Test | Setup | Expected |
|---|---|---|
| **A** Correct context | real retrieved evidence | answers correctly |
| **B** No context | evidence removed | **abstains** |
| **C** Wrong context | evidence from an unrelated paper | abstains / avoids the target |
| **D** Perturbed context | a fact deliberately altered | answer follows the **altered** value |
| **E** Summary only | title + abstract, no chunks | abstains unless the abstract truly has the fact |
| **F** Retrieved chunks only | production path | same as A |
| **G/H** Document switch | conflicting fact across two papers | each paper yields its own answer |
| **I/J** Reverse switch | same, order reversed, state cleared | unchanged by order |

Rules enforced **in code**, not just described here:

- A correct answer under **no context** is recorded as
  `PRIOR_KNOWLEDGE_OR_LEAKAGE`, never as a pass.
- If wrong-context evidence coincidentally contains the target value, the case
  is marked `TEST_ARTIFACT` — not counted as grounding.
- A perturbation is only scored when the token was actually present; otherwise
  the test reports `NOT_APPLICABLE`.
- A document switch counts **only** when both documents give a specific,
  different, non-abstained answer. An answer/abstain pair is explicitly
  rejected and reported as `NOT_SATISFIED`.
- Question gold labels come from the chunk each question was generated from,
  established *before* retrieval runs — never judged after seeing the results.
- A question whose stated answer is not verbatim in its source passage is
  discarded rather than scored.

## 7. Failure taxonomy

Failures are classified, never collapsed into "RAG error" or "graph error".

**RAG:** `RETRIEVAL_FAILURE`, `GENERATION_FAILURE`, `GROUNDING_FAILURE`,
`CITATION_FAILURE`, `CONTEXT_INFLUENCE_FAILURE`, `PRIOR_KNOWLEDGE_OR_LEAKAGE`,
`CORRECT_ABSTENTION`, `TEST_ARTIFACT`.

**Concept Graph:** `EXTRACTION_FAILURE`, `NORMALIZATION_FAILURE`,
`RELATIONSHIP_FAILURE`, `PROVENANCE_FAILURE`, `DUPLICATION_FAILURE`,
`ISOLATION_FAILURE`, `PERSISTENCE_FAILURE`, `API_FAILURE`,
`FRONTEND_GRAPH_FAILURE`.

Note the distinction the harness relies on: when the gold chunk was never
retrieved, a wrong answer is a `RETRIEVAL_FAILURE`, not a grounding failure.

## 8. Verdicts

**RAG** — `NOT VERIFIED` / `PARTIALLY VERIFIED` / `STRONGLY VERIFIED RAG`.
`STRONGLY VERIFIED RAG` requires *all* of: correct-context answers largely
succeed, no-context predominantly abstains, perturbed evidence changes the
answer, and a genuine conflicting document switch passes in both orders.

**Concept Graph** — `NOT FUNCTIONAL` / `PARTIALLY FUNCTIONAL` / `FUNCTIONAL`.

Reports state results as *experimental evidence of causal document grounding*.
They do not claim proof that the model lacks prior knowledge of a paper — that
is not establishable from black-box testing.

## 9. Cost and determinism

A full run makes roughly 40–80 Groq calls (question generation, conflict
search, and 6 causal tests per question). Groq rate limits will trigger SDK
retries and slow a run; reduce `--questions` if needed.

Generation is not perfectly deterministic even at low temperature, so causal
pass rates vary a little between runs. The parts that must be deterministic —
normalization, citation validation, evidence budgeting, scope resolution, graph
write idempotency — are covered by the pytest suites, which use stubbed model
responses so they never depend on model behaviour.

## 10. Provider quota — read this before a full run

The Groq free tier enforces **two** limits, and only one of them is visible in
the response headers:

| Limit | Value (free tier) | Header | Behaviour |
|---|---|---|---|
| Tokens per minute (TPM) | 8,000 | `x-ratelimit-remaining-tokens` | pace and retry — handled by `common/throttle.py` |
| Tokens per **day** (TPD) | 200,000 | *not exposed* | retrying does not help until the window rolls |

Two things make the daily budget disappear faster than expected:

1. **Groq reserves the full `max_tokens` at admission**, not the tokens
   actually generated. A `max_tokens=4096` call costs 4,096 output tokens of
   quota even if the answer is ten words.
2. **`openai/gpt-oss-120b` is a reasoning model** — its hidden chain of thought
   is billed as completion tokens, so real usage sits near the reservation.

A full causal run (2 documents × 2 questions × 6 tests, plus question
generation and the conflict search) costs roughly **60–100k tokens**, so two or
three full runs exhaust a day's budget.

**Practical guidance**

- Start with `--retrieval-only`. It needs a handful of LLM calls for question
  generation and none for generation tests.
- Use `--questions 2` or fewer for the causal phase.
- `--tpm N` only paces the per-minute window; it cannot stretch the daily cap.
- Check that no earlier run is still alive before starting a new one. On
  Windows `pkill` does not kill native processes — use
  `Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like "*run_evaluation*" }`
  and `Stop-Process`. Concurrent runs share one quota and will starve each
  other while each reports rate-limit failures that look like pipeline bugs.

When the daily quota is exhausted the harness now aborts the LLM phases with an
explicit `Groq daily token quota (TPD) exhausted` error instead of retrying.
That distinction matters for reading a report: a run cut short this way has an
**environment limit**, not a RAG defect, and its causal section must be read as
*not executed* rather than *failed*.
