"""
arXiv API client.

Uses the arXiv Atom API (no key required):
  http://export.arxiv.org/api/query?search_query=...&max_results=N

Returns normalized data compatible with PaperCreate.
"""
import re
import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Optional

import httpx

ARXIV_BASE_URL = "https://export.arxiv.org/api/query"
ARXIV_NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "arxiv": "http://arxiv.org/schemas/atom",
    "opensearch": "http://a9.com/-/spec/opensearch/1.1/",
}


def _extract_arxiv_id(entry_id: str) -> str:
    """Extract plain arXiv ID from URL like http://arxiv.org/abs/2310.12345v1."""
    match = re.search(r"abs/([^v]+)", entry_id)
    return match.group(1) if match else entry_id


def _parse_entry(entry: ET.Element) -> Optional[Dict[str, Any]]:
    def tag(name: str, ns: str = "atom") -> Optional[ET.Element]:
        return entry.find(f"{ns}:{name}", ARXIV_NS)

    def tag_text(name: str, ns: str = "atom") -> Optional[str]:
        el = tag(name, ns)
        return el.text.strip() if el is not None and el.text else None

    raw_id = tag_text("id")
    if not raw_id:
        return None

    arxiv_id = _extract_arxiv_id(raw_id)

    title = tag_text("title")
    if not title:
        return None
    title = " ".join(title.split())  # normalise whitespace

    abstract = tag_text("summary")
    if abstract:
        abstract = " ".join(abstract.split())

    published = tag_text("published")
    year = int(published[:4]) if published and len(published) >= 4 else None

    # Authors
    authors = [
        a.find("atom:name", ARXIV_NS).text.strip()
        for a in entry.findall("atom:author", ARXIV_NS)
        if a.find("atom:name", ARXIV_NS) is not None
    ]

    # Journal ref (venue)
    journal_ref_el = entry.find("arxiv:journal_ref", ARXIV_NS)
    venue = journal_ref_el.text.strip() if journal_ref_el is not None and journal_ref_el.text else "arXiv"

    # PDF URL — always available for arXiv
    pdf_url = f"https://arxiv.org/pdf/{arxiv_id}.pdf"

    # DOI
    doi_el = entry.find("arxiv:doi", ARXIV_NS)
    doi = doi_el.text.strip() if doi_el is not None and doi_el.text else None

    return {
        "arxiv_id": arxiv_id,
        "doi": doi,
        "semantic_scholar_id": None,
        "title": title,
        "abstract": abstract or "",
        "publication_year": year,
        "venue": venue,
        "pdf_url": pdf_url,
        "source": "arXiv",
        "citation_count": None,
        "reference_count": None,
        # Extra field for search results display (not persisted)
        "openalex_id": None,
    }


class ArxivClient:
    async def search_works(self, query: str, limit: int = 20) -> List[Dict[str, Any]]:
        params = {
            "search_query": f"all:{query}",
            "max_results": limit,
            "sortBy": "relevance",
        }
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            response = await client.get(ARXIV_BASE_URL, params=params)
            response.raise_for_status()

        root = ET.fromstring(response.text)
        entries = root.findall("atom:entry", ARXIV_NS)
        results = []
        for entry in entries:
            parsed = _parse_entry(entry)
            if parsed:
                results.append(parsed)
        return results

    async def get_work_by_id(self, arxiv_id: str) -> Dict[str, Any]:
        """Fetch a single arXiv paper by its ID (e.g. '2310.12345')."""
        params = {
            "id_list": arxiv_id,
            "max_results": 1,
        }
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            response = await client.get(ARXIV_BASE_URL, params=params)
            response.raise_for_status()

        root = ET.fromstring(response.text)
        entries = root.findall("atom:entry", ARXIV_NS)
        if not entries:
            raise ValueError(f"arXiv paper not found: {arxiv_id}")
        parsed = _parse_entry(entries[0])
        if not parsed:
            raise ValueError(f"Failed to parse arXiv entry: {arxiv_id}")
        return parsed


arxiv_client = ArxivClient()
