# Branch Verification Report

This report confirms the mapping of repository branches to their respective architectural implementations before beginning benchmark operations.

## DBMS-Centric Architecture (Baseline)
* **Branch Name:** `main`
* **Commit SHA:** `eeb2bc40bfc601a1bd1f9e47d56920225c24023f`
* **Detected Architecture:** DBMS-Centric
* **Relevant Database Technologies:** PostgreSQL (asyncpg), Neo4j (graph/vector database).
* **Retrieval Implementation:** Scope-aware dense/vector retrieval utilizing local Sentence Transformer embeddings and Neo4j cosine similarity (`vector.similarity.cosine`).
* **Ingestion Implementation:** PyMuPDF text extraction followed by local embedding generation and Neo4j graph storage (chunks and LLM-extracted concepts).
* **Confirmation:** The `main` branch matches the intended DBMS-centric architecture.

## Cloud-Oriented Architecture
* **Branch Name:** `saira-cloud` (referred to as `cloud`)
* **Commit SHA:** `aa193852cc2a379c81aeb2d4a089d587adcc41ba`
* **Detected Architecture:** Cloud-Oriented
* **Relevant Database Technologies:** PostgreSQL exclusively (no Neo4j), augmented by Blob Storage (S3/Local) for Markdown.
* **Retrieval Implementation:** PostgreSQL Full-Text Search utilizing `TSVECTOR`, `GIN` indexes, and `ts_rank_cd`. Employs intent-to-section query expansion over structured fields.
* **Ingestion Implementation:** PyMuPDF text extraction followed by LLM-based structured knowledge compilation (producing wiki-style Markdown pages with provenance) stored in Postgres and Blob storage.
* **Confirmation:** The `saira-cloud` branch matches the intended Cloud-oriented architecture.
