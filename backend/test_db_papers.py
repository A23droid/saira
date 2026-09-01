import asyncio
from app.db.session import AsyncSessionLocal
from app.services.paper_service import paper_service
from sqlalchemy import select
from app.models.paper import Paper

async def check():
    async with AsyncSessionLocal() as session:
        papers = await paper_service.get_all_papers(session, limit=10)
        for p in papers:
            print(f"Paper: {p.title}")
            print(f"  DOI: {p.doi}")
            print(f"  ArXiv: {p.arxiv_id}")
            print(f"  S2: {p.semantic_scholar_id}")
            
if __name__ == "__main__":
    asyncio.run(check())
