import httpx
import asyncio

async def test():
    async with httpx.AsyncClient(base_url="http://127.0.0.1:8000") as client:
        # We need auth. Let's just create a test user or login
        res = await client.post("/api/v1/auth/login", data={"username": "test@test.com", "password": "password"})
        if res.status_code != 200:
            print("Login failed, attempting to register...")
            await client.post("/api/v1/auth/register", json={"email": "test@test.com", "password": "password", "name": "Test"})
            res = await client.post("/api/v1/auth/login", data={"username": "test@test.com", "password": "password"})
            
        print("Login status:", res.status_code)
        
        # Get a paper
        res = await client.get("/api/v1/papers/?limit=1")
        papers = res.json()
        if not papers:
            print("No papers found in DB")
            return
            
        paper_id = papers[0]["id"]
        print(f"Testing paper: {paper_id}")
        
        # Hit similar
        res = await client.get(f"/api/v1/papers/{paper_id}/similar")
        print(f"Similar endpoint status: {res.status_code}")
        print(f"Similar endpoint body: {res.text}")

if __name__ == "__main__":
    asyncio.run(test())
