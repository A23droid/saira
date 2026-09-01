import httpx
from typing import Any, Dict

OPENALEX_BASE_URL = "https://api.openalex.org"

class OpenAlexClient:
    def __init__(self, email: str = "your_email@example.com"):
        self.email = email
        self.headers = {"User-Agent": f"SAIRA/1.0 (mailto:{self.email})"}

    async def search_works(self, query: str, limit: int = 20, page: int = 1) -> list[Dict[str, Any]]:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{OPENALEX_BASE_URL}/works",
                params={"search": query, "per-page": limit, "page": page, "mailto": self.email},
                headers=self.headers
            )
            response.raise_for_status()
            data = response.json()
            return data.get("results", [])

    async def get_work_by_id(self, openalex_id: str) -> Dict[str, Any]:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{OPENALEX_BASE_URL}/works/{openalex_id}",
                params={"mailto": self.email},
                headers=self.headers
            )
            response.raise_for_status()
            return response.json()

    async def get_similar_works(self, openalex_id: str, limit: int = 20, page: int = 1) -> list[Dict[str, Any]]:
        """
        Fetch related works from OpenAlex. 
        Works via 'related_to:{id}' where id is an OpenAlex ID.
        If a DOI URL is passed, it resolves to an OpenAlex ID first.
        """
        async with httpx.AsyncClient() as client:
            try:
                if openalex_id.startswith("https://doi.org/"):
                    # Resolve DOI to OpenAlex Work ID first
                    work_res = await client.get(
                        f"{OPENALEX_BASE_URL}/works/{openalex_id}",
                        params={"mailto": self.email},
                        headers=self.headers
                    )
                    work_res.raise_for_status()
                    openalex_id = work_res.json().get("id", "").split("/")[-1]
                    
                    if not openalex_id:
                        return []

                response = await client.get(
                    f"{OPENALEX_BASE_URL}/works",
                    params={
                        "filter": f"related_to:{openalex_id}", 
                        "per-page": limit, 
                        "page": page, 
                        "mailto": self.email
                    },
                    headers=self.headers
                )
                response.raise_for_status()
                data = response.json()
                return data.get("results", [])
            except Exception as e:
                return []

openalex_client = OpenAlexClient()
