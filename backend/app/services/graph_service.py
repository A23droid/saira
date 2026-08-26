import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.project_paper import ProjectPaper
from app.models.paper import Paper
from app.models.paper_analysis import PaperAnalysis
from app.schemas.paper import CitationGraphData, ConceptGraphData

class GraphService:
    async def get_project_citation_graph(self, session: AsyncSession, project_id: uuid.UUID) -> CitationGraphData:
        # 1. Fetch all project papers
        stmt = select(Paper).join(ProjectPaper).where(ProjectPaper.project_id == project_id)
        project_papers = list(await session.scalars(stmt))
        
        nodes = []
        edges = []
        
        if not project_papers:
            return {"nodes": nodes, "edges": edges}
            
        project_paper_ids = set()
        
        # Add project papers as group 1
        for p in project_papers:
            project_paper_ids.add(str(p.id))
            nodes.append({
                "id": str(p.id),
                "label": p.title[:60] + ("..." if len(p.title) > 60 else ""),
                "year": p.publication_year,
                "group": 1
            })
            
        # We will use the local project papers to see if they cite each other as a simplistic mock.
        # Generate some mock relationships based on year to ensure directed edges make sense
        sorted_papers = sorted(project_papers, key=lambda x: x.publication_year or 0)
        for i in range(len(sorted_papers)):
            for j in range(i + 1, len(sorted_papers)):
                # Newer cites older
                edges.append({
                    "source": str(sorted_papers[j].id),
                    "target": str(sorted_papers[i].id)
                })
                
        # To simulate external papers, let's create a few dummy nodes if we have at least one paper
        if project_papers:
            base_p = project_papers[0]
            ext1_id = f"ext-1-{base_p.id}"
            ext2_id = f"ext-2-{base_p.id}"
            nodes.append({"id": ext1_id, "label": "External Foundation Paper", "year": (base_p.publication_year or 2023) - 2, "group": 2})
            nodes.append({"id": ext2_id, "label": "Recent Follow-up Work", "year": (base_p.publication_year or 2023) + 1, "group": 3})
            
            edges.append({"source": str(base_p.id), "target": ext1_id})
            edges.append({"source": ext2_id, "target": str(base_p.id)})
            
        return {"nodes": nodes, "edges": edges}

    async def get_project_concept_graph(self, session: AsyncSession, project_id: uuid.UUID) -> ConceptGraphData:
        # 1. Fetch all project papers with their analysis
        stmt = (
            select(Paper)
            .join(ProjectPaper)
            .where(ProjectPaper.project_id == project_id)
            .options(selectinload(Paper.analysis))
        )
        project_papers = list(await session.scalars(stmt))
        
        nodes = []
        edges = []
        node_map = {} # label_type -> id
        
        for p in project_papers:
            paper_node_id = str(p.id)
            nodes.append({
                "id": paper_node_id,
                "label": p.title[:50] + ("..." if len(p.title) > 50 else ""),
                "type": "paper"
            })
            
            analysis = p.analysis
            if not analysis:
                continue
                
            # Helper to add concepts and edges
            def add_concepts(items, concept_type, edge_label):
                if not items:
                    return
                # Extract list from dict or list
                item_list = []
                if isinstance(items, dict):
                    item_list = list(items.keys())
                elif isinstance(items, list):
                    item_list = items
                    
                for item in item_list:
                    if not isinstance(item, str):
                        continue
                    clean_item = item.strip().title()
                    if not clean_item:
                        continue
                    
                    key = f"{clean_item}_{concept_type}"
                    if key not in node_map:
                        concept_id = str(uuid.uuid4())
                        node_map[key] = concept_id
                        nodes.append({
                            "id": concept_id,
                            "label": clean_item,
                            "type": concept_type
                        })
                    else:
                        concept_id = node_map[key]
                        
                    edges.append({
                        "source": paper_node_id,
                        "target": concept_id,
                        "label": edge_label
                    })

            if len(analysis) > 0:
                a = analysis[0]
                add_concepts(a.models, "model", "uses_model")
                add_concepts(a.algorithms, "method", "uses_method")
                add_concepts(a.datasets, "dataset", "evaluated_on")
                add_concepts(a.results, "result", "reports")
                
                # Add glossary as generic concepts
                if getattr(a, 'glossary', None) and isinstance(a.glossary, dict):
                    add_concepts(list(a.glossary.keys()), "concept", "discusses")
                
        return {"nodes": nodes, "edges": edges}

graph_service = GraphService()
