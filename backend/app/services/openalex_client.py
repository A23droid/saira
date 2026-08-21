import httpx
from typing import Any, Dict

OPENALEX_BASE_URL = "https://api.openalex.org"

class OpenAlexClient:
    def __init__(self, email: str = "your_email@example.com"):
        self.email = email
        self.headers = {"User-Agent": f"SAIRA/1.0 (mailto:{self.email})"}

    async def search_works(self, query: str, limit: int = 20) -> list[Dict[str, Any]]:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{OPENALEX_BASE_URL}/works",
                params={"search": query, "per-page": limit, "mailto": self.email},
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

openalex_client = OpenAlexClient()
