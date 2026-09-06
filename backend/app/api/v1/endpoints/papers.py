import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_current_user
from app.models.user import User
from app.models.project import Project
from app.models.project_paper import ProjectPaper
from app.schemas.paper import PaperCreate, PaperUpdate, PaperResponse
from app.schemas.project import ProjectResponse
from app.schemas.graph import CitationResponse, DependencyResponse, ResearchMapResponse
from app.services.paper_service import paper_service
from app.db.neo4j_client import get_neo4j_session
from app.services.indexing_jobs import FAILED_STATES, ensure_indexed, is_ask_ai_ready

router = APIRouter()


@router.get("/", response_model=list[PaperResponse])
async def get_papers(
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    return await paper_service.get_all_papers(session=db, skip=skip, limit=limit)


@router.post("/", response_model=PaperResponse, status_code=status.HTTP_201_CREATED)
async def create_paper(
    paper_in: PaperCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    paper = await paper_service.create_paper(session=db, paper_in=paper_in)
    await ensure_indexed(paper.id)
    return paper


@router.get("/{paper_id}", response_model=PaperResponse)
async def get_paper(
    paper_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    paper = await paper_service.get_paper_by_id(session=db, paper_id=paper_id)
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")
        
    # Opening a paper deliberately does NOT start indexing. Ingestion is
    # triggered where a paper enters the library (search ingest, add-to-project),
    # so "what started this job" is unambiguous and merely viewing a paper has
    # no side effects. Papers predating automatic ingestion are handled once by
    # backend/scripts/backfill_indexing.py; a failed one is retried explicitly
    # through GET /papers/{id}/indexing-status?retry=true.
    return paper


@router.get("/{paper_id}/indexing-status")
async def get_indexing_status(
    paper_id: uuid.UUID,
    retry: bool = False,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    """Poll target for the frontend, and the controlled retry for a failure.

    `ask_ai_ready` is derived from the persisted status only — it is never
    true for a paper whose chunks do not exist.
    """
    paper = await paper_service.get_paper_by_id(session=db, paper_id=paper_id)
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")

    status_now = paper.indexing_status or "not_indexed"
    if retry and status_now in FAILED_STATES:
        status_now = await ensure_indexed(paper_id, force=True)

    return {
        "paper_id": str(paper.id),
        "indexing_status": status_now,
        "indexing_error": paper.indexing_error,
        "ask_ai_ready": is_ask_ai_ready(status_now),
        "can_retry": status_now in FAILED_STATES,
    }


@router.patch("/{paper_id}", response_model=PaperResponse)
async def update_paper(
    paper_id: uuid.UUID,
    paper_in: PaperUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    paper = await paper_service.get_paper_by_id(session=db, paper_id=paper_id)
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")
    return await paper_service.update_paper(session=db, db_paper=paper, paper_in=paper_in)


@router.delete("/{paper_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_paper(
    paper_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    paper = await paper_service.get_paper_by_id(session=db, paper_id=paper_id)
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")
    await paper_service.delete_paper(session=db, db_paper=paper)
    return None


@router.get("/{paper_id}/projects", response_model=list[ProjectResponse])
async def get_paper_projects(
    paper_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    stmt = (
        select(Project)
        .join(ProjectPaper)
        .where(ProjectPaper.paper_id == paper_id, Project.user_id == current_user.id)
    )
    result = await db.scalars(stmt)
    return list(result.all())


@router.get("/{paper_id}/similar", response_model=list[PaperResponse])
async def get_similar_papers(
    paper_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    paper = await paper_service.get_paper_by_id(session=db, paper_id=paper_id)
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")

    from app.services.search_service import search_service
    similar = await search_service.get_similar_papers(db, paper, limit=5)

    return similar


from app.schemas.graph import CitationResponse, DependencyResponse, ResearchMapResponse, GraphCitationsResponse, GraphConceptsResponse

# ...

@router.get("/{paper_id}/citations", response_model=GraphCitationsResponse)
async def get_citations(
    paper_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    neo_session: AsyncSession = Depends(get_neo4j_session),
    current_user: User = Depends(get_current_user),
) -> Any:
    paper = await paper_service.get_paper_by_id(session=db, paper_id=paper_id)
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")

    from app.services.neo4j_service import neo4j_service
    from app.services.citation_service import citation_service
    import asyncio
    
    citations = await neo4j_service.get_citations(neo_session, str(paper_id))
    references = await neo4j_service.get_references(neo_session, str(paper_id))
    
    # If we have very few citations and references, it might not be synced yet
    if len(citations) + len(references) == 0:
        # Trigger background sync using a detached db session since the current one closes
        async def background_sync(pid: str):
            from app.db.session import AsyncSessionLocal
            async with AsyncSessionLocal() as bg_db:
                await citation_service.sync_paper_citations(bg_db, pid)
                
        asyncio.create_task(background_sync(str(paper_id)))
        
    return {"citations": citations, "references": references}

@router.get("/{paper_id}/concepts", response_model=GraphConceptsResponse)
async def get_concepts(
    paper_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    neo_session: AsyncSession = Depends(get_neo4j_session),
    current_user: User = Depends(get_current_user),
) -> Any:
    """Concept subgraph for exactly one paper.

    Scope is enforced in the Cypher (`MATCH (p:Paper {id})-[:HAS_CONCEPT]->`),
    so a concept shared with another paper contributes only this paper's edge.
    Nothing here relies on the frontend filtering the response.
    """
    paper = await paper_service.get_paper_by_id(session=db, paper_id=paper_id)
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")

    from app.services.neo4j_service import neo4j_service
    from app.services.concept_service import concept_service
    import asyncio

    data = await neo4j_service.get_paper_concept_graph(neo_session, str(paper_id))
    concepts = data.get("concepts", [])

    if not concepts:
        # Nothing extracted yet — kick off a background sync so the next load
        # has data. Uses its own session because this request's session closes.
        async def background_sync(pid: str):
            from app.db.session import AsyncSessionLocal
            async with AsyncSessionLocal() as bg_db:
                await concept_service.sync_paper_concepts(bg_db, pid)

        asyncio.create_task(background_sync(str(paper_id)))

    nodes = [{"id": str(paper_id), "label": paper.title or "Paper", "type": "Paper"}]
    edges = []

    for c in concepts:
        nodes.append({
            "id": c["id"],
            "label": c.get("name") or "",
            "type": "Concept",
        })
        edges.append({
            "source": str(paper_id),
            "target": c["id"],
            "label": "HAS_CONCEPT",
        })

    # Concept-to-concept edges asserted by this paper.
    concept_ids = {c["id"] for c in concepts}
    for r in data.get("relations", []):
        if r["source"] in concept_ids and r["target"] in concept_ids:
            edges.append({
                "source": r["source"],
                "target": r["target"],
                "label": r.get("type") or "RELATES_TO",
            })

    return {"nodes": nodes, "edges": edges}


@router.get("/{paper_id}/dependencies", response_model=list[DependencyResponse])
async def get_dependencies(
    paper_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    neo_session: AsyncSession = Depends(get_neo4j_session),
    current_user: User = Depends(get_current_user),
) -> Any:
    paper = await paper_service.get_paper_by_id(session=db, paper_id=paper_id)
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")

    from app.services.neo4j_service import neo4j_service
    deps = await neo4j_service.get_dependencies(neo_session, str(paper_id))
    return deps


@router.get("/{paper_id}/research-map", response_model=ResearchMapResponse)
async def get_research_map(
    paper_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    neo_session: AsyncSession = Depends(get_neo4j_session),
    current_user: User = Depends(get_current_user),
) -> Any:
    paper = await paper_service.get_paper_by_id(session=db, paper_id=paper_id)
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")

    from app.services.neo4j_service import neo4j_service
    from app.services.search_service import search_service

    citations = await neo4j_service.get_citations(neo_session, str(paper_id))
    deps = await neo4j_service.get_dependencies(neo_session, str(paper_id))
    similar = await search_service.get_similar_papers(db, paper, limit=5)

    return {
        "paper": paper,
        "citations": citations,
        "dependencies": deps,
        "similar": similar
    }

