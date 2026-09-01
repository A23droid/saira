import asyncio
import logging
from app.db.session import AsyncSessionLocal
from app.services.paper_service import paper_service
from app.services.search_service import search_service

# Setup logging to see the logger outputs
logging.basicConfig(level=logging.INFO)

async def test_search():
    async with AsyncSessionLocal() as session:
        # Get one paper from DB
        papers = await paper_service.get_all_papers(session, limit=1)
        if not papers:
            print("No papers in DB.")
            return
            
        paper = papers[0]
        print(f"\n=============================================")
        print(f"Testing Paper ID: {paper.id}")
        print(f"Title: {paper.title}")
        print(f"Identifiers: DOI={paper.doi}, ArXiv={paper.arxiv_id}, S2={paper.semantic_scholar_id}")
        print(f"=============================================\n")
        
        try:
            results = await search_service.get_similar_papers(paper, limit=5)
            print(f"\n=============================================")
            print(f"Final valid candidates returned: {len(results)}")
            for idx, r in enumerate(results):
                print(f"{idx+1}. {r.get('title')} - {r.get('pdf_url')}")
            print(f"=============================================\n")
        except Exception as e:
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    import os
    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    asyncio.run(test_search())
