import logging
import uuid
from typing import List, Dict, Any, Optional
from neo4j import AsyncSession

from app.db.neo4j_client import neo4j_client

logger = logging.getLogger(__name__)

class Neo4jService:
    async def upsert_paper(self, session: AsyncSession, paper_dict: Dict[str, Any]) -> None:
        """
        Upsert a Paper node.
        Uses PostgreSQL UUID as the primary identifier.
        """
        query = """
        MERGE (p:Paper {id: $id})
        SET p.doi = $doi,
            p.arxiv_id = $arxiv_id,
            p.semantic_scholar_id = $semantic_scholar_id,
            p.title = $title,
            p.publication_year = $publication_year,
            p.venue = $venue,
            p.citation_count = $citation_count
        """
        await session.run(query, **paper_dict)

    async def add_citation(self, session: AsyncSession, source_id: str, target_id: str) -> None:
        """
        Create a CITES relationship from source paper to target paper.
        """
        query = """
        MATCH (s:Paper {id: $source_id})
        MATCH (t:Paper {id: $target_id})
        MERGE (s)-[:CITES]->(t)
        """
        await session.run(query, source_id=source_id, target_id=target_id)

    async def add_dependency(self, session: AsyncSession, paper_id: str, dep_id: str, dep_type: str, dep_label: str, rel_props: Optional[Dict[str, Any]] = None) -> None:
        """
        Add a generic dependency to a paper (e.g. Method, Dataset, Concept).
        """
        # We use a dynamic node label via f-string since labels cannot be parameterized directly in Cypher.
        # Ensure dep_type is safe.
        valid_types = {"Method", "Dataset", "Concept", "Author"}
        if dep_type not in valid_types:
            raise ValueError(f"Invalid dependency type: {dep_type}")
            
        rel_map = {
            "Method": "USES_METHOD",
            "Dataset": "USES_DATASET",
            "Concept": "HAS_CONCEPT",
            "Author": "AUTHORED_BY"
        }
        rel_type = rel_map[dep_type]
            
        query = f"""
        MATCH (p:Paper {{id: $paper_id}})
        MERGE (d:{dep_type} {{id: $dep_id}})
        ON CREATE SET d.name = $dep_label
        MERGE (p)-[r:{rel_type}]->(d)
        SET r += $rel_props
        """
        await session.run(query, paper_id=paper_id, dep_id=dep_id, dep_label=dep_label, rel_props=rel_props or {})
        
    async def get_citations(self, session: AsyncSession, paper_id: str) -> List[Dict[str, Any]]:
        """
        Get papers cited by this paper.
        """
        query = """
        MATCH (p:Paper {id: $paper_id})-[:CITES]->(c:Paper)
        RETURN c.id AS id, c.title AS title, c.publication_year AS year, c.doi AS doi, c.arxiv_id AS arxiv_id, c.semantic_scholar_id AS semantic_scholar_id, c.has_pdf AS has_pdf
        """
        result = await session.run(query, paper_id=paper_id)
        records = await result.data()
        return records

    async def get_references(self, session: AsyncSession, paper_id: str) -> List[Dict[str, Any]]:
        """
        Get papers that cite this paper.
        """
        query = """
        MATCH (p:Paper {id: $paper_id})<-[:CITES]-(c:Paper)
        RETURN c.id AS id, c.title AS title, c.publication_year AS year, c.doi AS doi, c.arxiv_id AS arxiv_id, c.semantic_scholar_id AS semantic_scholar_id, c.has_pdf AS has_pdf
        """
        result = await session.run(query, paper_id=paper_id)
        records = await result.data()
        return records

    async def get_dependencies(self, session: AsyncSession, paper_id: str) -> List[Dict[str, Any]]:
        """
        Get dependencies (methods, datasets, concepts) for this paper.
        """
        query = """
        MATCH (p:Paper {id: $paper_id})-[r]->(d)
        WHERE type(r) IN ['USES_METHOD', 'USES_DATASET', 'HAS_CONCEPT']
        RETURN d.id AS id, d.name AS name, labels(d)[0] AS type, properties(r) AS rel_props
        """
        result = await session.run(query, paper_id=paper_id)
        return await result.data()
        
    async def get_similar_candidates(self, session: AsyncSession, paper_id: str, limit: int = 20) -> List[Dict[str, Any]]:
        """
        Find similar papers based on graph traversal (e.g., co-citations, shared concepts).
        Returns a list of dicts that can be used to rank candidates.
        """
        # Find papers that share citations, methods, or concepts.
        query = """
        MATCH (p:Paper {id: $paper_id})-[r1]->(shared)<-[r2]-(other:Paper)
        WHERE type(r1) IN ['CITES', 'USES_METHOD', 'HAS_CONCEPT']
          AND type(r1) = type(r2)
          AND p <> other
        WITH other, count(shared) AS shared_count
        ORDER BY shared_count DESC
        LIMIT $limit
        RETURN other.id AS id, other.title AS title, other.doi AS doi, 
               other.arxiv_id AS arxiv_id, other.semantic_scholar_id AS semantic_scholar_id,
               shared_count
        """
        result = await session.run(query, paper_id=paper_id, limit=limit)
        return await result.data()

    # ── Vector retrieval ──────────────────────────────────────────────────────

    async def search_chunks(
        self,
        session: AsyncSession,
        paper_ids: List[str],
        query_embedding: List[float],
        top_k: int = 5,
    ) -> List[Dict[str, Any]]:
        """Scope-first similarity search — the single retrieval primitive.

        The scope restriction is applied in the MATCH, before ranking, so the
        top-k is computed *within* the allowed papers. Querying the global
        vector index and filtering afterwards would silently return fewer than
        k (or zero) in-scope results whenever unrelated papers dominate the
        neighbourhood, which is both a recall bug and a scope-leak risk.

        Chunks with no embedding are excluded rather than scored as 0.0, so a
        partially-indexed paper degrades to fewer results instead of surfacing
        empty evidence that looks like a real hit.
        """
        if not paper_ids:
            return []
        query = """
        MATCH (p:Paper)-[:HAS_CHUNK]->(chunk:Chunk)
        WHERE p.id IN $paper_ids AND chunk.embedding IS NOT NULL
        WITH chunk, p, vector.similarity.cosine(chunk.embedding, $embedding) AS score
        WHERE score IS NOT NULL
        ORDER BY score DESC
        LIMIT $top_k
        RETURN chunk.id          AS id,
               chunk.text        AS text,
               chunk.page        AS page,
               chunk.chunk_index AS chunk_index,
               p.id              AS paper_id,
               p.title           AS paper_title,
               score
        """
        result = await session.run(
            query, paper_ids=list(paper_ids), embedding=query_embedding, top_k=top_k
        )
        return await result.data()

    async def get_relevant_chunks(self, session: AsyncSession, paper_id: str, query_embedding: List[float], top_k: int = 5) -> List[Dict[str, Any]]:
        """Backwards-compatible single-paper wrapper over `search_chunks`."""
        return await self.search_chunks(session, [paper_id], query_embedding, top_k)

    async def get_project_relevant_chunks(self, session: AsyncSession, paper_ids: List[str], query_embedding: List[float], top_k: int = 10) -> List[Dict[str, Any]]:
        """Backwards-compatible multi-paper wrapper over `search_chunks`."""
        return await self.search_chunks(session, paper_ids, query_embedding, top_k)

    # ── Concept graph ─────────────────────────────────────────────────────────

    async def upsert_concepts(
        self,
        session: AsyncSession,
        paper_id: str,
        concepts: List[Dict[str, Any]],
    ) -> int:
        """Idempotently attach concepts to a paper, preserving provenance.

        Identity is the caller-supplied deterministic `id` (a uuid5 of the
        canonical name), so the same concept seen in ten papers is one node
        with ten edges — not ten nodes. Both node and edge use MERGE, so
        re-ingesting a paper updates the existing edge instead of adding a
        parallel one; running this twice cannot double the graph.

        Provenance (`pages`, `chunk_ids`, `evidence`) lives on the *edge*, not
        the node, because it is a fact about this paper's use of the concept
        rather than about the concept itself.
        """
        if not concepts:
            return 0
        query = """
        MATCH (p:Paper {id: $paper_id})
        UNWIND $concepts AS c
        MERGE (n:Concept {id: c.id})
          ON CREATE SET n.name = c.name, n.created_at = datetime()
        SET n.name    = c.name,
            n.aliases = CASE
                          WHEN n.aliases IS NULL THEN c.aliases
                          ELSE [a IN n.aliases WHERE NOT a IN c.aliases] + c.aliases
                        END
        MERGE (p)-[r:HAS_CONCEPT]->(n)
        SET r.importance = c.importance,
            r.pages      = c.pages,
            r.chunk_ids  = c.chunk_ids,
            r.evidence   = c.evidence,
            r.updated_at = datetime()
        RETURN count(*) AS n
        """
        result = await session.run(query, paper_id=paper_id, concepts=concepts)
        rec = await result.single()
        return rec["n"] if rec else 0

    async def upsert_concept_relations(
        self,
        session: AsyncSession,
        paper_id: str,
        relations: List[Dict[str, Any]],
    ) -> int:
        """Create concept→concept edges asserted by a specific paper.

        The relationship type is stored as a property on a single `RELATES_TO`
        edge rather than as a dynamic Cypher label. A dynamic label would need
        string interpolation per type and would make "all relations for this
        paper" an open-ended query; keeping one edge type with a `type`
        property keeps deletion and re-ingestion exact.

        Edges are keyed by `(source, target, type, paper_id)` via MERGE, so the
        same assertion from the same paper is stored once however many times
        the paper is re-ingested, while the *same* relation asserted by a
        *different* paper is kept separately with its own provenance.
        """
        if not relations:
            return 0
        query = """
        UNWIND $relations AS rel
        MATCH (s:Concept {id: rel.source_id})
        MATCH (t:Concept {id: rel.target_id})
        MERGE (s)-[r:RELATES_TO {type: rel.type, paper_id: $paper_id}]->(t)
        SET r.evidence   = rel.evidence,
            r.chunk_ids  = rel.chunk_ids,
            r.pages      = rel.pages,
            r.updated_at = datetime()
        RETURN count(*) AS n
        """
        result = await session.run(query, paper_id=paper_id, relations=relations)
        rec = await result.single()
        return rec["n"] if rec else 0

    async def clear_paper_concepts(self, session: AsyncSession, paper_id: str) -> None:
        """Detach a paper from the concept graph without touching other papers.

        Deletes only this paper's HAS_CONCEPT edges and only the RELATES_TO
        edges this paper asserted. Concept nodes are left in place because they
        are shared; orphans are collected separately by `prune_orphan_concepts`.
        This is what makes a forced re-index a replace rather than an append.
        """
        await session.run(
            "MATCH (:Paper {id: $paper_id})-[r:HAS_CONCEPT]->() DELETE r",
            paper_id=paper_id,
        )
        await session.run(
            "MATCH ()-[r:RELATES_TO {paper_id: $paper_id}]->() DELETE r",
            paper_id=paper_id,
        )

    async def prune_orphan_concepts(self, session: AsyncSession) -> int:
        """Delete Concept nodes no paper references any more."""
        result = await session.run(
            """
            MATCH (c:Concept)
            WHERE NOT (:Paper)-[:HAS_CONCEPT]->(c)
            DETACH DELETE c
            RETURN count(c) AS n
            """
        )
        rec = await result.single()
        return rec["n"] if rec else 0

    async def get_paper_concept_graph(self, session: AsyncSession, paper_id: str) -> Dict[str, Any]:
        """Concepts and concept-relations for exactly one paper."""
        node_q = """
        MATCH (p:Paper {id: $paper_id})-[r:HAS_CONCEPT]->(c:Concept)
        RETURN c.id AS id, c.name AS name, c.aliases AS aliases,
               r.importance AS importance, r.pages AS pages,
               r.chunk_ids AS chunk_ids, r.evidence AS evidence
        ORDER BY r.importance DESC
        """
        rel_q = """
        MATCH (p:Paper {id: $paper_id})-[:HAS_CONCEPT]->(s:Concept)
        MATCH (p)-[:HAS_CONCEPT]->(t:Concept)
        MATCH (s)-[r:RELATES_TO {paper_id: $paper_id}]->(t)
        RETURN s.id AS source, t.id AS target, r.type AS type,
               r.evidence AS evidence, r.pages AS pages, r.chunk_ids AS chunk_ids
        """
        nodes = await (await session.run(node_q, paper_id=paper_id)).data()
        rels = await (await session.run(rel_q, paper_id=paper_id)).data()
        return {"concepts": nodes, "relations": rels}

    async def get_project_concept_graph(
        self, session: AsyncSession, paper_ids: List[str]
    ) -> Dict[str, Any]:
        """Concepts and relations across a project's papers, scope-enforced.

        Both the concept query and the relation query are constrained by
        `paper_ids`, so a concept shared with a paper outside the project
        contributes only the in-project edges. Relations additionally require
        both endpoints to be in-project, which prevents an edge dangling to a
        concept the caller is not allowed to see.
        """
        if not paper_ids:
            return {"concepts": [], "relations": [], "papers": []}

        node_q = """
        MATCH (p:Paper)-[r:HAS_CONCEPT]->(c:Concept)
        WHERE p.id IN $paper_ids
        WITH c, collect(DISTINCT p.id) AS paper_ids,
             max(r.importance) AS importance,
             reduce(acc = [], x IN collect(r.pages) | acc + coalesce(x, [])) AS pages
        RETURN c.id AS id, c.name AS name, c.aliases AS aliases,
               importance, paper_ids, pages
        ORDER BY importance DESC
        """
        rel_q = """
        MATCH (s:Concept)<-[:HAS_CONCEPT]-(p:Paper)-[:HAS_CONCEPT]->(t:Concept)
        WHERE p.id IN $paper_ids
        MATCH (s)-[r:RELATES_TO]->(t)
        WHERE r.paper_id IN $paper_ids
        RETURN DISTINCT s.id AS source, t.id AS target, r.type AS type,
               r.paper_id AS paper_id, r.evidence AS evidence
        """
        paper_q = """
        MATCH (p:Paper) WHERE p.id IN $paper_ids
        RETURN p.id AS id, p.title AS title
        """
        nodes = await (await session.run(node_q, paper_ids=paper_ids)).data()
        rels = await (await session.run(rel_q, paper_ids=paper_ids)).data()
        papers = await (await session.run(paper_q, paper_ids=paper_ids)).data()
        return {"concepts": nodes, "relations": rels, "papers": papers}

    async def graph_stats(self, session: AsyncSession) -> Dict[str, Any]:
        """Counts used by the evaluation harness and integrity tests."""
        q = """
        CALL () { MATCH (c:Concept) RETURN count(c) AS concepts }
        CALL () { MATCH (:Paper)-[r:HAS_CONCEPT]->() RETURN count(r) AS has_concept }
        CALL () { MATCH ()-[r:RELATES_TO]->() RETURN count(r) AS relations }
        CALL () { MATCH (c:Concept) WHERE NOT (:Paper)-[:HAS_CONCEPT]->(c)
                  RETURN count(c) AS orphan_concepts }
        CALL () { MATCH (ch:Chunk) RETURN count(ch) AS chunks }
        CALL () { MATCH (p:Paper) RETURN count(p) AS papers }
        RETURN concepts, has_concept, relations, orphan_concepts, chunks, papers
        """
        try:
            rec = await (await session.run(q)).single()
            return dict(rec) if rec else {}
        except Exception:
            # Older Neo4j versions require CALL { } without the empty arg list.
            q_legacy = q.replace("CALL ()", "CALL ")
            rec = await (await session.run(q_legacy)).single()
            return dict(rec) if rec else {}


neo4j_service = Neo4jService()
