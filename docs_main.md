# SAIRA DBMS-Centric Architecture Audit Report

This document contains a comprehensive audit of the DBMS-centric (`main` branch) implementation of the SAIRA system, prepared for the comparative evaluation research paper.

## 1. DBMS VERSION EXECUTIVE SUMMARY
The `main` branch implements a **hybrid database architecture**, utilizing **PostgreSQL** (via `asyncpg` and SQLAlchemy) for relational metadata, user management, and structured state, combined with **Neo4j** for vector storage, chunk-level retrieval, and the concept graph. 

Contrary to potential inferences about a purely PostgreSQL-based approach, this implementation **does not use PostgreSQL full-text search (FTS)** or `pgvector`. Instead, all semantic retrieval and graph traversals are executed within Neo4j using `vector.similarity.cosine`. The system uses an external AI provider (Groq) for LLM generation and local Sentence Transformers for text embeddings.

## 2. COMPLETE ARCHITECTURE
The system architecture derived from the source code consists of:
- **Backend Framework:** FastAPI (async) with Python 3.13.
- **Relational Database:** PostgreSQL (accessed via SQLAlchemy async session).
- **Graph/Vector Database:** Neo4j (accessed via `neo4j` async driver).
- **PDF Processing:** Local extraction using PyMuPDF (`fitz`), executed in thread pools.
- **Embedding Generation:** Local Sentence Transformers (`SentenceTransformer`).
- **LLM Layer:** Centralized `ai_router.py` mapping specific tasks to Groq models via `groq_service.py`.
- **Background Jobs:** In-process deduped asyncio tasks (`indexing_jobs.py`) rather than a dedicated queue like Celery.
- **Evaluation:** Custom evaluation harness (`evaluation/`) for RAG quality and latency tracking.

## 3. DATABASE ARCHITECTURE
- **PostgreSQL (`app/db/session.py`):** Manages users, projects, chat sessions, paper metadata, and paper analyses (JSONB for structured extractions like datasets and models). Uses async connection pooling (`pool_size`, `max_overflow`).
- **Neo4j (`app/services/neo4j_service.py`):** Manages `(Paper)-[:HAS_CHUNK]->(Chunk)` and `(Paper)-[:HAS_CONCEPT]->(Concept)` relationships. 
- **Query Patterns:** PostgreSQL handles point lookups and authorization. Neo4j handles all similarity searches. There is no evidence of N+1 query risks in retrieval as scope resolution does a bulk IN query on PostgreSQL, passing an array of UUIDs to Neo4j.
- **Bottleneck Risks:** Embedding generation is CPU-bound. Although offloaded to `asyncio.to_thread`, heavy concurrent ingestion could exhaust host CPU. Neo4j vector similarity scales linearly with chunks if no HNSW index is strictly enforced (which requires checking the Neo4j schema migrations, though `search_chunks` performs a brute-force cosine similarity within a pre-filtered scope).

## 4. PAPER INGESTION PIPELINE
Trace in `backend/app/services/research_indexer.py`:
1. **API Trigger:** Paper creation or addition to project triggers `indexing_jobs.ensure_indexed`.
2. **Download:** Async HTTP GET to resolve and download PDF bytes (`httpx`), validated by magic bytes.
3. **Extraction & Chunking:** `asyncio.to_thread(_extract_and_chunk)` uses PyMuPDF to extract text, followed by a custom character-based semantic chunker prioritizing paragraphs.
4. **Embedding:** `asyncio.to_thread(_embed_chunks)` runs chunks through the local SentenceTransformer.
5. **Persistence (Neo4j):** `_store_chunks_in_neo4j` writes chunks and embeddings to Neo4j idempotently.
6. **Concept Extraction:** Triggers `concept_service.sync_paper_concepts` which uses LLMs (Groq) to extract concepts from chunks, singularize them, and store them back in Neo4j with provenance (`chunk_ids`).

## 5. KNOWLEDGE REPRESENTATION
- **Structured Knowledge:** Stored in PostgreSQL `paper_analyses` (summary, novelty, datasets, models, results) as Text or JSONB.
- **Vector Knowledge:** Stored in Neo4j `Chunk` nodes containing `text`, `page`, `chunk_index`, and `embedding`.
- **Concept Knowledge:** Stored in Neo4j `Concept` nodes connected to `Paper` via `HAS_CONCEPT`. Contains provenance tracing directly back to `Chunk` IDs.
- **Note:** Remnants of older architectures are gone; the current active pipeline strictly uses PostgreSQL + Neo4j. No flat markdown stores are used for active retrieval.

## 6. RETRIEVAL PIPELINE
Trace in `backend/app/services/retrieval_service.py` and `neo4j_service.py`:
1. **Scope Resolution:** The caller requests a scope (`paper` or `project`). `resolve_project_scope` queries PostgreSQL to verify ownership and fetches all `paper_ids` in the project.
2. **Embedding:** The query is embedded locally.
3. **Scope-First Vector Search:** Calls `neo4j_service.search_chunks`. The Cypher query explicitly filters `WHERE p.id IN $paper_ids` **before** computing `vector.similarity.cosine` and taking `LIMIT $top_k`. This is a critical design choice preventing scope leakage and preserving top-k density.

## 7. LLM PIPELINE
- **Provider:** Groq via `app/services/groq_service.py`.
- **Router:** `app/services/ai_router.py` strictly routes tasks (QA, Summary, Concept Extraction) to designated models (e.g., `GROQ_PRIMARY_MODEL`, `GROQ_EXTRACTION_MODEL`).
- **Usage:** Used heavily during ingestion (concept extraction, structured paper analysis) and at runtime (retrieval-augmented generation for chat).
- **Error Handling:** Centralized parsing of timeouts and rate limits, converting them to clean HTTP 5xx/429 responses.

## 8. PAPER CHAT / PROJECT CHAT
Both workflows are unified under `retrieval_service.retrieve` and `ai_router.answer_scoped`.
- **Paper Chat (`chat.py`):** Passes a `RetrievalScope` of type `paper`. The LLM is grounded only in chunks from that specific paper.
- **Project Chat (`project_ai.py`):** Passes a `RetrievalScope` of type `project`. PostgreSQL resolves this to a list of all papers in the project. Neo4j retrieves chunks across the entire project. The LLM synthesizes answers across multiple papers.
- **Difference:** The *only* architectural difference is the `RetrievalScope` passed to the retrieval layer.

## 9. OTHER RESEARCH FEATURES
- **Similar Papers:** IMPLEMENTED via graph traversal (`get_similar_candidates` in Neo4j).
- **Comparisons:** IMPLEMENTED (`comparisons.py` endpoint).
- **Literature Review Synthesis:** IMPLEMENTED (`project_ai.py` generates reviews).
- **Collections:** IMPLEMENTED (`collections.py`).
- **Trending/Analytics:** IMPLEMENTED.

## 10. SECURITY AND SCOPE
Scope enforcement is strictly **server-side** and relies on PostgreSQL relational constraints.
- `_get_verified_project` in API endpoints verifies `user_id == current_user.id`.
- The frontend never provides the list of IDs for retrieval; it provides a `project_id`, which the backend expands into a verified list of `paper_ids`.
- Neo4j queries always require `paper_ids` to be explicitly passed; global un-scoped searches are not exposed.

## 11. PERFORMANCE-RELEVANT COMPONENTS
- **Local Embedding CPU Cost:** `embedding_service.py` blocks CPU. Concurrent ingestions could starve the host. (A: Measurable now).
- **Neo4j Vector Search:** In-scope cosine similarity without HNSW index acceleration might degrade as project sizes grow. (B: Measurable with instrumentation).
- **PostgreSQL Pooling:** Asyncpg handles high concurrency well, but transaction locks on chat sessions might bottleneck under stress. (B: Measurable with instrumentation).
- **Groq Network Calls:** External API latency is highly variable. (A: Measurable now).

## 12. EXISTING BENCHMARK EVIDENCE
**NO EXISTING PERFORMANCE DATA FOUND** for throughput, load, or scalability. 
- There is a functional evaluation harness (`evaluation/`) that computes RAG accuracy (grounding, leakage) and reports single-request retrieval latency (`latency_ms`).
- There is an ad-hoc script (`scripts/evaluate_retrieval.py`) that prints query latency.
- There are no automated load tests (e.g., Locust, k6) or concurrent throughput benchmarks.

## 13. REQUIRED DBMS EXPERIMENTS
To compare against the cloud architecture, the following workloads must be implemented:
1. **Ingestion Throughput:** Measure time to ingest a corpus of 100 PDFs concurrently (factors in PyMuPDF and local embeddings).
2. **Project Chat Latency under Load:** Measure P95 latency of project-scoped queries as the project size scales from 10 to 1,000 papers.
3. **Concurrent Retrieval Throughput:** Run 50 concurrent searches and measure requests-per-second (RPS) and database CPU utilization.

## 14. REQUIRED METRICS
- **P95 / P99 End-to-End Latency:** Crucial for user experience in chat.
- **Ingestion Time per Paper:** To evaluate the local chunking/embedding pipeline against a cloud-native equivalent.
- **CPU / Memory Utilization:** To prove how the DBMS/hybrid architecture utilizes host resources during vector operations compared to managed cloud services.
- **Neo4j Query Time:** Specifically isolating the `search_chunks` execution time.

## 15. CONTROLLED VARIABLES
For a fair DBMS vs. Cloud comparison, the following must be identical:
- The exact same PDF corpus.
- The exact same SentenceTransformer model and chunking parameters (`chunk_size=1500`, `overlap=300`).
- The exact same LLM provider (Groq), models, and prompts.
- The exact same `top_k` parameters (`RAG_TOP_K_PAPER`, `RAG_TOP_K_PROJECT`).

## 16. PAPER SECTION MAPPING
- **DBMS Architecture:** Fully writeable now. The code proves a Postgres/Neo4j hybrid.
- **System Architecture:** Fully writeable now.
- **Evaluation Metrics:** Writeable (Accuracy exists, throughput must be defined).
- **Benchmarking Procedure / Results:** **MISSING**. Must be executed.

## 17. PAPER-READY DBMS METHODOLOGY

### DBMS-Based Architecture
The baseline database-centric architecture of SAIRA employs a hybrid persistence model designed to strictly enforce multi-tenant boundaries while enabling semantic search and graph traversals. Relational metadata, user ownership, and structured knowledge extractions are persisted in PostgreSQL, utilizing connection pooling via an asynchronous SQLAlchemy engine. To support retrieval-augmented generation (RAG), the system utilizes Neo4j as a combined vector and graph store. 

During paper ingestion, documents are locally processed using PyMuPDF and chunked using a character-based semantic strategy. Chunks are embedded locally via Sentence Transformers and written to Neo4j. Concept extraction is subsequently performed over these chunks via an external Large Language Model (LLM), with extracted entities and relations persisted as a graph topology directly mapped to their originating text chunks.

Crucially, the retrieval pipeline prioritizes scope over global similarity to prevent data leakage. When a query is issued against a project, PostgreSQL first resolves the user's project ownership and compiles an explicit array of permissible paper identifiers. This array is passed to Neo4j, which executes a filtered cosine similarity search strictly within the bounded subgraph, ensuring that ranking algorithms operate only on authorized data.

### Experimental Setup — DBMS Baseline
The DBMS baseline will be deployed on a controlled host environment running PostgreSQL 15+ and Neo4j 5+. All local inference operations, including PyMuPDF extraction and Sentence Transformer embedding generation, will utilize the host's CPU allocation. LLM generation requests will be routed to a standardized external provider (Groq) to isolate database-layer performance from generation latency. 

### Performance Measurement Requirements
To isolate the performance characteristics of the hybrid DBMS architecture, measurements will decouple ingestion costs from retrieval costs. Ingestion metrics will track total processing time per document and host CPU utilization, reflecting the cost of local parsing and vector serialization. Retrieval metrics will capture mean, P95, and P99 latencies for scoped vector searches, specifically isolating the Neo4j query execution time from external LLM generation time. Throughput will be evaluated by subjecting the retrieval endpoints to increasing concurrent request loads until failure or severe latency degradation occurs.

## 18. MISSING WORK BEFORE EXPERIMENTS
1. Create a `locustfile.py` or `k6` script to simulate concurrent user loads for ingestion and chat.
2. Instrument `neo4j_service.py` to log raw DB query time separately from embedding time.
3. Prepare a standardized benchmark corpus of N papers to ensure repeatability.

## 19. REVIEWER-STYLE CONCERNS
- **Vector Search Scalability:** Neo4j is performing brute-force cosine similarity on a filtered subset. If a project contains thousands of papers, this linear scan will degrade compared to an HNSW index.
- **Local Embedding Bottleneck:** Using `asyncio.to_thread` for CPU-bound embedding generation inside a web worker prevents event loop blocking, but concurrent requests will still saturate the host CPU, drastically reducing retrieval throughput under load.
- **Missing FTS:** The paper abstract mentioned PostgreSQL Full-Text Search, but the actual `main` branch uses solely vector search via Neo4j. This discrepancy must be addressed in the paper.

## 20. EXACT NEXT STEPS
1. Accept this audit as the definitive state of the `main` branch.
2. Proceed to review the `cloud` branch to document its architectural differences.
3. Build the concurrent load-testing scripts outlined in Section 18.
4. Execute the benchmarks and populate the results sections of the paper.
