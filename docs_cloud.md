# SAIRA Cloud-Oriented Architecture Audit Report

This document contains a comprehensive audit of the cloud-centric (`saira-cloud` branch) implementation of the SAIRA system, prepared for the comparative evaluation research paper.

## 1. DBMS VERSION EXECUTIVE SUMMARY
The `saira-cloud` branch implements a **pure PostgreSQL + Blob Storage architecture**, aggressively ripping out Neo4j, vector embeddings, and local SentenceTransformers. 

The system relies exclusively on **PostgreSQL Full-Text Search (FTS)** using `TSVECTOR`, `GIN` indexes, and `ts_rank_cd` for retrieval, alongside S3/local-disk for persisting compiled Markdown knowledge pages. Semantic retrieval has been replaced with LLM-assisted knowledge compilation (summarizing the document into a structured wiki) combined with keyword intent mapping (e.g., mapping the keyword "problem" to the "Introduction" section in Postgres).

## 2. COMPLETE ARCHITECTURE
The system architecture derived from the source code consists of:
- **Backend Framework:** FastAPI (async) with Python 3.13.
- **Relational & Search Database:** PostgreSQL (accessed via SQLAlchemy async session).
- **Blob Storage:** `KnowledgeStore` abstraction, supporting `LocalKnowledgeStore` and `S3KnowledgeStore` for Markdown files.
- **PDF Processing:** Local extraction using PyMuPDF (`fitz`), executed in thread pools.
- **Knowledge Compiler:** `knowledge_compiler.py` extracts text and uses Groq LLMs to compile structured "wiki pages" with strictly verified provenance.
- **LLM Layer:** Centralized `ai_router.py` mapping specific tasks to Groq models via `llm_provider.py`.
- **Background Jobs:** In-process deduped asyncio tasks (`indexing_jobs.py`).
- **Evaluation:** Custom evaluation harness (`evaluation/`) for RAG quality and latency tracking.

## 3. DATABASE ARCHITECTURE
- **PostgreSQL (`app/db/session.py` & `app/models/knowledge.py`):** The singular database. It holds metadata, chat history, and the new `knowledge_entries` table.
- **FTS Search Index:** The `knowledge_entries` table utilizes a `Computed()` column `search_vector` of type `TSVECTOR`. This vector is generated via `setweight(to_tsvector('english', ...), 'A')` prioritizing titles over sections over body text. A `GIN` index (`ix_knowledge_entries_search`) accelerates retrieval.
- **Graph Alternative:** The concept graph is now modeled relationally via `PaperConcept` and `ConceptRelation` tables natively in PostgreSQL.
- **Query Patterns:** Retrieval is a single SQL query joining `knowledge_entries` to `papers`, filtering by `paper_id = ANY(...)`, and ranking by `ts_rank_cd(ke.search_vector, q.query, 32)`.
- **Bottleneck Risks:** Since local embeddings are removed, host CPU is freed up. However, heavily concurrent `to_tsquery` operations over large `GIN` indexes under load might strain PostgreSQL CPU and memory.

## 4. PAPER INGESTION PIPELINE
Trace in `backend/app/services/research_indexer.py`:
1. **API Trigger:** Paper creation or addition to project triggers `indexing_jobs.ensure_indexed`.
2. **Download:** Async HTTP GET to resolve and download PDF bytes, validated by magic bytes.
3. **Knowledge Compilation:** `knowledge_compiler.compile_paper` is invoked.
4. **Extraction:** PyMuPDF extracts text and detects section headings (heuristic-based).
5. **Source Units:** Text is split into verbatim `_UNIT_WORDS = 400` chunk sizes.
6. **LLM Wiki Generation:** The compiler sends prioritized sections to the LLM to generate structured fields.
7. **Verification:** The compiler maps every LLM-generated quote back to a source unit to ensure zero hallucination.
8. **Persistence:** The compiled page is saved to S3/Disk (`knowledge_store`), and `knowledge_entries` are inserted into PostgreSQL.

## 5. KNOWLEDGE REPRESENTATION
- **Knowledge Store (`knowledge_store.py`):** A portable Markdown representation of the paper's extracted knowledge, persisted in S3 (AWS) or local disk.
- **Knowledge Entries (`knowledge_entries` table):** Source text units, compiled metadata, concepts, and topics are all flattened into this table.
- **Provenance:** Every compiled entry in PostgreSQL contains a `provenance` JSONB blob linking it explicitly to a page and verbatim source text.
- **Note:** Neo4j and vector embeddings are completely removed.

## 6. RETRIEVAL PIPELINE
Trace in `backend/app/services/knowledge_retriever.py`:
1. **Scope Resolution:** `resolve_project_scope` strictly bounds the retrieval to a list of `paper_ids`.
2. **Intent Expansion:** `expand_with_sections` maps generic user queries (e.g., "what is the method") to targeted section filters (e.g., "Methodology") to overcome the semantic gap of pure keyword search.
3. **Query Construction:** `build_tsquery` ORs the terms together to maximize recall on long questions.
4. **PostgreSQL FTS Search:** Executes `ts_rank_cd` restricted to the explicit `paper_ids` list. It ranks the exact wording of the paper higher than compiled summaries via `_KIND_WEIGHTS`.
5. **Fallback:** If `ts_rank_cd` finds 0 matches (e.g., due to stemmed acronyms), it gracefully falls back to an `ILIKE` substring search.

## 7. LLM PIPELINE
- **Provider:** Groq via `app/services/llm_provider.py`.
- **Usage:** Replaces the vector pipeline. The LLM is used heavily during the initial ingestion phase (`knowledge_compiler`) to pre-compute summaries, datasets, limitations, and concepts. 
- **Cost Offset:** By pre-compiling knowledge with the LLM, the retrieval phase no longer requires an embedding model inference step.

## 8. PAPER CHAT / PROJECT CHAT
Both workflows are unified under `knowledge_retriever.search`.
- **Paper Chat (`chat.py`):** Uses a `paper` scope. Translates to a Postgres query where `paper_id = ANY(ARRAY[single_id])`.
- **Project Chat (`project_ai.py`):** Uses a `project` scope. Translates to a Postgres query where `paper_id = ANY(ARRAY[project_ids])`.
- **Difference:** The only difference is the size of the array passed to the PostgreSQL `ANY(...)` filter.

## 9. OTHER RESEARCH FEATURES
- **Similar Papers:** Relies on shared Postgres `ConceptRelation` joins.
- **Comparisons:** IMPLEMENTED.
- **Literature Review Synthesis:** IMPLEMENTED.
- **Collections:** IMPLEMENTED.
- **Trending/Analytics:** IMPLEMENTED.

## 10. SECURITY AND SCOPE
Scope enforcement remains strictly **server-side**:
- The API explicitly resolves project ownership via PostgreSQL before accepting any retrieval request.
- The PostgreSQL `WHERE ke.paper_id = ANY(CAST(:paper_ids AS uuid[]))` clause in `knowledge_retriever.py` ensures that FTS matching physically cannot traverse out of scope.

## 11. PERFORMANCE-RELEVANT COMPONENTS
- **PostgreSQL GIN Index:** Handles all ranking and searching. Heavy read-concurrency could bottleneck on Postgres shared buffers or CPU. (B: Measurable with instrumentation).
- **Knowledge Compilation (LLM):** Ingestion is entirely network-bound to Groq. (A: Measurable now).
- **Blob Storage I/O:** Reading/writing Markdown to S3 incurs network latency via `boto3`, offloaded to thread pools. (A: Measurable now).
- **CPU Freed:** Local embedding models are removed, drastically reducing host CPU pressure compared to the `main` branch.

## 12. EXISTING BENCHMARK EVIDENCE
**NO EXISTING PERFORMANCE DATA FOUND** for throughput, load, or scalability. 
- The `evaluation/` harness tracks RAG accuracy and single-request `latency_ms`.
- There are no concurrent load test scripts (Locust/k6) simulating cloud traffic.

## 13. REQUIRED CLOUD EXPERIMENTS
To compare against the DBMS baseline, the following workloads must be executed:
1. **Ingestion Throughput:** Measure time to ingest a 100-paper corpus. The bottleneck shifts from local CPU (embeddings) to Network I/O (Groq/S3).
2. **PostgreSQL FTS Latency under Load:** Measure P95 latency of `ts_rank_cd` queries as the `knowledge_entries` table scales to millions of rows.
3. **Concurrent Retrieval Throughput:** Run 50 concurrent searches to measure RPS against the PostgreSQL GIN index.

## 14. REQUIRED METRICS
- **P95 / P99 End-to-End Latency:** To see if FTS retrieval is faster/slower than Neo4j vector retrieval.
- **Ingestion Time per Paper:** Evaluates the trade-off of pre-compiling knowledge via LLM vs computing embeddings locally.
- **Database CPU Utilization:** Crucial to determine if FTS text ranking is more expensive than vector cosine similarity.
- **Storage Footprint:** Compare Neo4j vector blob sizes to PostgreSQL TSVECTOR + S3 Markdown sizes.

## 15. CONTROLLED VARIABLES
For a fair DBMS vs. Cloud comparison, the following must be identical:
- The exact same PDF corpus.
- The exact same LLM provider (Groq), models, and prompts.
- The exact same `top_k` parameters for evidence injection.
- The hardware hosting PostgreSQL must be identical in both tests.

## 16. PAPER SECTION MAPPING
- **Cloud Architecture:** Fully writeable now. The code proves a PostgreSQL FTS + S3 Blob storage paradigm replacing the graph vector store.
- **System Architecture:** Writeable, highlighting the dual-branch structural pivot.
- **Evaluation Metrics:** Writeable.
- **Benchmarking Procedure / Results:** **MISSING**. Must be executed.

## 17. PAPER-READY CLOUD METHODOLOGY

### Cloud-Oriented Architecture
The cloud-oriented architecture of SAIRA adopts a stateless, pure-PostgreSQL paradigm augmented by blob storage, explicitly discarding dedicated vector databases and graph engines. In this architecture, semantic retrieval is replaced by a combination of Large Language Model (LLM) knowledge compilation and PostgreSQL Full-Text Search (FTS).

During paper ingestion, documents are parsed locally via PyMuPDF. Rather than generating and indexing dense embeddings, the text is passed to an LLM-driven compiler. The compiler synthesizes the document into structured knowledge fields (e.g., findings, datasets, limitations) and rigidly maps every generated assertion back to a verbatim source quote to prevent hallucination. This compiled "knowledge page" is persisted as a Markdown file to an object store (e.g., Amazon S3). Concurrently, both the verbatim source units and the compiled summaries are inserted into a PostgreSQL `knowledge_entries` table. 

Retrieval relies exclusively on PostgreSQL. The `knowledge_entries` table employs a dynamically computed `TSVECTOR` column, indexing titles, section headers, and body text with varying weights. A `GIN` index accelerates search. To bridge the semantic gap of pure keyword search, user queries undergo intent expansion (e.g., mapping the keyword "problem" to the "Introduction" section metadata) before being transformed into a `tsquery`. Scope isolation is enforced at the database level by bounding the FTS `ts_rank_cd` function within a strictly verified `WHERE paper_id = ANY(...)` clause.

### Experimental Setup — Cloud Baseline
The cloud baseline will be evaluated on the same host environment as the DBMS baseline. PostgreSQL will act as the sole database, and the S3 Knowledge Store will be simulated locally or routed to a standard bucket to measure network I/O penalties. Ingestion will rely on the Groq API for knowledge compilation, bypassing host CPU constraints previously imposed by local embedding generation.

### Performance Measurement Requirements
Metrics will focus on the latency and throughput trade-offs of FTS vs. Vector Search. Ingestion time per document will quantify the latency of LLM-based compilation against local vectorization. Retrieval metrics will measure the P95 latency of `ts_rank_cd` executions over the `GIN` index as the number of rows scales, identifying whether keyword ranking on a relational database under concurrent load outperforms or bottlenecks compared to an in-memory vector traversal.

## 18. MISSING WORK BEFORE EXPERIMENTS
1. Construct load testing scripts (Locust/k6) targeting the cloud branch endpoints.
2. Instrument `knowledge_retriever.py` to log the raw execution time of the `_SELECT` PostgreSQL FTS query.
3. Align the evaluation corpus precisely with the one used for the `main` branch.

## 19. REVIEWER-STYLE CONCERNS
- **FTS Recall vs. Semantic Recall:** Reviewers may question whether substituting vector embeddings with keyword FTS + Intent Expansion fundamentally degrades RAG answer quality. The accuracy metrics from the `evaluation/` harness must explicitly defend this choice.
- **Ingestion Latency:** Passing the entire document through an LLM to "compile" knowledge is significantly slower and more expensive per-paper than calculating an embedding. The throughput numbers must transparently reflect this upfront cost.

## 20. EXACT NEXT STEPS
1. Accept this audit as the definitive state of the `saira-cloud` branch.
2. Develop the identical load-testing scripts necessary to evaluate both branches.
3. Execute the concurrent throughput and latency benchmarks.
4. Synthesize the findings into the Results section of the research paper.
