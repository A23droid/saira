"""
Graph views over the knowledge layer.

These endpoints used to read Neo4j. They now read `paper_concepts`,
`concept_relations` and `paper_citations` in PostgreSQL. The wire shapes
(`ConceptGraphData`, `CitationGraphData`, `GraphCitationsResponse`,
`DependencyResponse`) are unchanged, so `concept-graph.tsx` and
`citation-graph.tsx` did not need touching.

A graph database was never load-bearing for these views. Every query here is a
one- or two-hop lookup keyed on a paper or a concept — the shape a relational
join handles perfectly well. The traversal Neo4j was actually good at
(`get_similar_candidates`, arbitrary-depth co-citation) is the one feature that
had to be reimplemented rather than translated; see
`search_service.get_similar_papers`, which now ranks by shared concept count.

One behaviour deliberately changed: `get_project_citation_graph` used to
fabricate its edges. It sorted the project's papers by year, asserted that
every newer paper cited every older one, and appended two invented nodes
labelled "External Foundation Paper" and "Recent Follow-up Work". None of that
came from data. It now returns real citation edges and an empty graph when
none have been synced, because a citation graph that invents citations is
worse than one that admits it is empty.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge import ConceptRelation, PaperCitation, PaperConcept
from app.models.paper import Paper
from app.models.project_paper import ProjectPaper
from app.schemas.paper import CitationGraphData, ConceptGraphData

logger = logging.getLogger(__name__)


def _truncate(label: str, limit: int = 60) -> str:
    label = label or "Untitled paper"
    return label[:limit] + ("..." if len(label) > limit else "")


class GraphService:

    # ── Per-paper views ───────────────────────────────────────────────────

    async def get_paper_concept_graph(
        self, session: AsyncSession, paper_id: uuid.UUID
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Concept subgraph for exactly one paper.

        Scope is enforced in the WHERE clause, so a concept shared with another
        paper contributes only this paper's edge. Nothing relies on the
        frontend filtering the response.
        """
        rows = list(await session.scalars(
            select(PaperConcept).where(PaperConcept.paper_id == paper_id)
        ))
        concepts = [
            {
                "id": c.concept_key,
                "name": c.name,
                "description": c.description,
                "pages": c.pages or [],
                "chunk_ids": c.entry_keys or [],
            }
            for c in rows
        ]
        keys = {c["id"] for c in concepts}

        rel_rows = list(await session.scalars(
            select(ConceptRelation).where(ConceptRelation.paper_id == paper_id)
        ))
        relations = [
            {"source": r.source_key, "target": r.target_key, "type": r.relation_type}
            for r in rel_rows
            if r.source_key in keys and r.target_key in keys
        ]
        return {"concepts": concepts, "relations": relations}

    async def get_paper_citations(
        self, session: AsyncSession, paper_id: uuid.UUID
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Return this paper's outbound references and inbound citations.

        The `citations` / `references` naming is inherited from the Neo4j
        implementation and preserved exactly: `citations` are works this paper
        points at, `references` are works pointing back at it.
        """
        rows = list(await session.scalars(
            select(PaperCitation).where(PaperCitation.paper_id == paper_id)
        ))

        def _shape(r: PaperCitation) -> Dict[str, Any]:
            return {
                "id": r.other_id,
                "title": r.other_title or "Untitled",
                "year": r.other_year,
                "doi": r.other_doi,
                "arxiv_id": r.other_arxiv_id,
                "semantic_scholar_id": r.other_semantic_scholar_id,
                "has_pdf": r.other_has_pdf,
            }

        return {
            "citations": [_shape(r) for r in rows if r.direction == "outbound"],
            "references": [_shape(r) for r in rows if r.direction == "inbound"],
        }

    async def get_paper_dependencies(
        self, session: AsyncSession, paper_id: uuid.UUID
    ) -> List[Dict[str, Any]]:
        """Methods/datasets/concepts this paper depends on.

        Neo4j modelled these as distinct node labels reached by
        `USES_METHOD` / `USES_DATASET` / `HAS_CONCEPT`. The knowledge layer
        keeps the same distinction in `paper_concepts.kind`, so the response
        shape is unchanged.
        """
        rows = list(await session.scalars(
            select(PaperConcept).where(PaperConcept.paper_id == paper_id)
        ))
        type_map = {"concept": "Concept", "method": "Method", "topic": "Topic"}
        return [
            {
                "id": c.concept_key,
                "name": c.name,
                "type": type_map.get(c.kind, "Concept"),
                "rel_props": {
                    "pages": c.pages or [],
                    "evidence": c.evidence,
                },
            }
            for c in rows
        ]

    # ── Project views ─────────────────────────────────────────────────────

    async def _project_paper_ids(
        self, session: AsyncSession, project_id: uuid.UUID
    ) -> List[uuid.UUID]:
        rows = await session.execute(
            select(ProjectPaper.paper_id).where(ProjectPaper.project_id == project_id)
        )
        return [r[0] for r in rows]

    async def get_project_citation_graph(
        self, session: AsyncSession, project_id: uuid.UUID
    ) -> CitationGraphData:
        """Real citation edges among and around the project's papers.

        Group 1 is a project paper; group 2 is an external work this project
        cites; group 3 is an external work citing into the project.
        """
        paper_ids = await self._project_paper_ids(session, project_id)
        nodes: List[Dict[str, Any]] = []
        edges: List[Dict[str, Any]] = []
        if not paper_ids:
            return {"nodes": nodes, "edges": edges}

        papers = list(await session.scalars(
            select(Paper).where(Paper.id.in_(paper_ids))
        ))
        local_ids = {str(p.id) for p in papers}
        for p in papers:
            nodes.append({
                "id": str(p.id),
                "label": _truncate(p.title),
                "year": p.publication_year,
                "group": 1,
            })

        citations = list(await session.scalars(
            select(PaperCitation).where(PaperCitation.paper_id.in_(paper_ids))
        ))

        seen_external: Dict[str, int] = {}
        for c in citations:
            local = str(c.paper_id)
            other = str(c.other_id)

            if other not in local_ids and other not in seen_external:
                # An external work is added once, grouped by which direction
                # first pulled it into the graph.
                seen_external[other] = 2 if c.direction == "outbound" else 3
                nodes.append({
                    "id": other,
                    "label": _truncate(c.other_title or "External work"),
                    "year": c.other_year,
                    "group": seen_external[other],
                })

            if c.direction == "outbound":
                edges.append({"source": local, "target": other})
            else:
                edges.append({"source": other, "target": local})

        return {"nodes": nodes, "edges": edges}

    async def get_project_concept_graph(
        self, session: AsyncSession, project_id: uuid.UUID
    ) -> ConceptGraphData:
        """Concept graph across every paper in the project.

        Shared concepts are what make this a graph rather than a set of stars:
        two papers asserting the same `concept_key` produce two edges into one
        node, which is exactly how the Neo4j version behaved.
        """
        paper_ids = await self._project_paper_ids(session, project_id)
        if not paper_ids:
            return {"nodes": [], "edges": []}

        papers = list(await session.scalars(
            select(Paper).where(Paper.id.in_(paper_ids))
        ))
        titles = {str(p.id): p.title for p in papers}

        nodes: List[Dict[str, Any]] = [
            {"id": pid, "label": _truncate(titles.get(pid)), "type": "paper"}
            for pid in (str(x) for x in paper_ids)
        ]
        edges: List[Dict[str, Any]] = []

        concept_rows = list(await session.scalars(
            select(PaperConcept).where(PaperConcept.paper_id.in_(paper_ids))
        ))
        concept_keys: set[str] = set()
        for c in concept_rows:
            if c.concept_key not in concept_keys:
                concept_keys.add(c.concept_key)
                nodes.append({
                    "id": c.concept_key,
                    "label": c.name,
                    "type": "concept",
                })
            edges.append({
                "source": str(c.paper_id),
                "target": c.concept_key,
                "label": "discusses",
            })

        rel_rows = list(await session.scalars(
            select(ConceptRelation).where(ConceptRelation.paper_id.in_(paper_ids))
        ))
        seen_edges: set[tuple] = set()
        for r in rel_rows:
            # Drop any edge whose endpoints are not both in the node list, so
            # the frontend never receives an edge pointing at a node it wasn't
            # given.
            if r.source_key not in concept_keys or r.target_key not in concept_keys:
                continue
            key = (r.source_key, r.target_key, r.relation_type)
            if key in seen_edges:
                continue
            seen_edges.add(key)
            edges.append({
                "source": r.source_key,
                "target": r.target_key,
                "label": (r.relation_type or "RELATES_TO").lower(),
            })

        return {"nodes": nodes, "edges": edges}


graph_service = GraphService()
