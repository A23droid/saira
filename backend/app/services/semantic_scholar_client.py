"""
Semantic Scholar API client.

Uses the public Semantic Scholar Academic Graph API (no API key required for
basic usage; rate limit is 100 req/5 min unauthenticated).

Search:  GET https://api.semanticscholar.org/graph/v1/paper/search
Single:  GET https://api.semanticscholar.org/graph/v1/paper/{paper_id}

Returns normalized data compatible with PaperCreate.
"""
import asyncio
from typing import Any, Dict, List, Optional

import httpx

S2_BASE_URL = "https://api.semanticscholar.org/graph/v1"
S2_FIELDS = "paperId,externalIds,title,abstract,year,venue,openAccessPdf,citationCount,referenceCount"


def _normalize_s2(paper: Dict[str, Any]) -> Dict[str, Any]:
    ext = paper.get("externalIds") or {}
    arxiv_id = ext.get("ArXiv")
    doi = ext.get("DOI")
    s2_id = paper.get("paperId")

    pdf_url = None
    oap = paper.get("openAccessPdf")
    if oap:
        pdf_url = oap.get("url")

    venue = paper.get("venue") or "Semantic Scholar"

    return {
        "arxiv_id": arxiv_id,
        "doi": doi,
        "semantic_scholar_id": s2_id,
        "title": paper.get("title") or "Untitled",
        "abstract": paper.get("abstract") or "",
        "publication_year": paper.get("year"),
        "venue": venue,
        "pdf_url": pdf_url,
        "source": "Semantic Scholar",
        "citation_count": paper.get("citationCount"),
        "reference_count": paper.get("referenceCount"),
        # Extra field for search results display (not persisted)
        "openalex_id": None,
    }


class SemanticScholarClient:
    def __init__(self) -> None:
        self.headers = {"User-Agent": "SAIRA/1.0 (research assistant)"}

    async def search_works(self, query: str, limit: int = 20) -> List[Dict[str, Any]]:
        params = {
            "query": query,
            "limit": min(limit, 100),
            "fields": S2_FIELDS,
        }
        for attempt in range(3):
            async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
                response = await client.get(
                    f"{S2_BASE_URL}/paper/search",
                    params=params,
                    headers=self.headers,
                )
                if response.status_code == 429:
                    await asyncio.sleep(2 ** attempt)
                    continue
                response.raise_for_status()
                data = response.json()
                papers = data.get("data", [])
                return [_normalize_s2(p) for p in papers if p.get("title")]
        return []

    async def get_work_by_id(self, paper_id: str) -> Dict[str, Any]:
        """
        Fetch a single paper by Semantic Scholar paper ID (40-char hex string)
        or by external IDs like 'arXiv:2310.12345', 'DOI:10.1234/...'
        """
        params = {"fields": S2_FIELDS}
        for attempt in range(3):
            async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
                response = await client.get(
                    f"{S2_BASE_URL}/paper/{paper_id}",
                    params=params,
                    headers=self.headers,
                )
                if response.status_code == 429:
                    await asyncio.sleep(2 ** attempt)
                    continue
                response.raise_for_status()
                data = response.json()
                return _normalize_s2(data)
        raise ValueError(f"Semantic Scholar paper not found or rate limited: {paper_id}")


semantic_scholar_client = SemanticScholarClient()
