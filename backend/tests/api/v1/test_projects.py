import pytest
from fastapi.testclient import TestClient
import uuid

from app.main import app
from app.api.deps import get_current_user, get_db
from app.models.user import User

# A module-level `TestClient(app)` opens a fresh event loop per request, while
# the async DB engine pools connections bound to the first loop — on Windows
# that surfaces as `'NoneType' object has no attribute 'send'`. A
# context-managed client keeps one portal (and one loop) for the whole module.
@pytest.fixture(scope="module")
def client():
    import asyncio
    with TestClient(app) as c:
        yield c
    # Release pooled connections bound to the portal's event loop.
    async def _dispose():
        from app.db.session import engine
        await engine.dispose()
    # Best effort: the portal's loop is already closing, so a failure to
    # drain it must not turn teardown into a test error.
    try:
        asyncio.run(_dispose())
    except Exception:
        pass


# The override must resolve to a user that actually exists: `projects.user_id`
# is a foreign key, so a freshly-minted random UUID makes every create fail
# with an IntegrityError rather than exercising the endpoint.
async def mock_get_current_user():
    from sqlalchemy import select
    from app.db.session import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        return await db.scalar(select(User).limit(1))

app.dependency_overrides[get_current_user] = mock_get_current_user


def _require_user():
    import asyncio
    from sqlalchemy import select
    from app.db.session import AsyncSessionLocal

    async def run():
        async with AsyncSessionLocal() as db:
            return await db.scalar(select(User).limit(1))
    try:
        return asyncio.run(run())
    except Exception:
        return None

def test_project_crud(client):
    # 1. Create Project
    response = client.post("/api/v1/projects/", json={
        "name": "My New Project",
        "description": "Test description",
        "color": "blue"
    })
    
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["name"] == "My New Project"
    assert body["description"] == "Test description"

    # Clean up so repeated runs do not accumulate rows.
    client.delete(f"/api/v1/projects/{body['id']}")

def test_paper_crud(client):
    # `papers.doi` is UNIQUE, so a fixed value makes the test pass once and
    # fail on every later run. A per-run DOI keeps it repeatable.
    doi = f"10.1234/test-{uuid.uuid4().hex[:12]}"
    response = client.post("/api/v1/papers/", json={
        "title": "A Great Paper",
        "doi": doi
    })
    
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["title"] == "A Great Paper"
    client.delete(f"/api/v1/papers/{body['id']}")

def test_add_remove_paper_from_project():
    # ... mock implementation
    pass

def test_project_ownership_authorization():
    # ... mock implementation
    pass

def test_duplicate_project_paper_association():
    # ... mock implementation
    pass

def test_project_paper_status_favorite_priority_updates():
    # ... mock implementation
    pass
