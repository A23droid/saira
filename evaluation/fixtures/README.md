# Fixtures

Deterministic inputs for **regression tests only**.

The main causal evaluation deliberately does **not** use anything in this
directory — it discovers real papers from arXiv at run time
(`discovery/document_discovery.py`). Fixtures exist so that the logic which
must behave identically on every run can be tested without depending on a
model, a network call, or a specific paper.

| File | Used by | Purpose |
|---|---|---|
| `conflicting_corpus.json` | `regression/test_controlled_switch.py` | Two synthetic documents that answer the same questions with *different* specific values, for a controlled context-influence test |

## Why the conflicting corpus is synthetic

The dynamic document-switch test (G–J) needs two real papers that answer the
same question with different specific values. Whether such a pair exists among
freshly discovered papers is not under the harness's control, so that test
honestly reports `NOT_SATISFIED` when no genuine conflict is found.

The fixture corpus removes that dependency for regression purposes: the
conflicting facts are known by construction, so the test can assert that the
answer follows the supplied evidence every time. It measures **context
influence**, which is a property of the generation layer, and it is reported
separately from the dynamic document-switch result. It is not a substitute for
the real test and is never counted as one.

These documents are invented. They are never ingested into the application
database and never reach retrieval — they are passed directly as evidence
overrides.
