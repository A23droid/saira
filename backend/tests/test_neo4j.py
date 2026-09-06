import pytest
from unittest.mock import AsyncMock, MagicMock
from app.services.neo4j_service import neo4j_service

@pytest.mark.asyncio
async def test_upsert_paper():
    mock_session = AsyncMock()
    mock_session.run = AsyncMock()
    
    paper_dict = {
        "id": "123",
        "doi": "10.1000/182",
        "arxiv_id": "2104.12345",
        "semantic_scholar_id": "abcd",
        "title": "Test Paper",
        "publication_year": 2024,
        "venue": "Test Venue",
        "citation_count": 0
    }
    
    await neo4j_service.upsert_paper(mock_session, paper_dict)
    
    # Verify run was called with correct query and params
    mock_session.run.assert_called_once()
    args, kwargs = mock_session.run.call_args
    assert "MERGE (p:Paper {id: $id})" in args[0]
    assert kwargs["id"] == "123"
    assert kwargs["doi"] == "10.1000/182"

@pytest.mark.asyncio
async def test_add_dependency():
    mock_session = AsyncMock()
    mock_session.run = AsyncMock()
    
    await neo4j_service.add_dependency(mock_session, "paper1", "method1", "Method", "Transformer")
    
    mock_session.run.assert_called_once()
    args, kwargs = mock_session.run.call_args
    assert "MERGE (d:Method {id: $dep_id})" in args[0]
    assert "USES_METHOD" in args[0]
    assert kwargs["paper_id"] == "paper1"
    assert kwargs["dep_label"] == "Transformer"
