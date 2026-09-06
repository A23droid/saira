import pytest
import uuid
from unittest.mock import AsyncMock, MagicMock, patch
from app.services.citation_service import citation_service, generate_external_id

@pytest.mark.asyncio
async def test_generate_external_id():
    # Test deterministic ID generation
    id1 = generate_external_id("semantic_scholar", "123")
    id2 = generate_external_id("semantic_scholar", "123")
    id3 = generate_external_id("semantic_scholar", "456")
    
    assert id1 == id2
    assert id1 != id3

@pytest.mark.asyncio
async def test_sync_paper_citations_no_db_paper():
    # Test when paper is not found in DB
    mock_db = AsyncMock()
    mock_db.scalar.return_value = None
    
    with patch("app.services.citation_service.logger.error") as mock_logger:
        await citation_service.sync_paper_citations(mock_db, str(uuid.uuid4()))
        mock_logger.assert_called_once()
        assert "not found in DB" in mock_logger.call_args[0][0]

@pytest.mark.asyncio
@patch("app.services.citation_service.semantic_scholar_client")
@patch("app.services.citation_service.neo4j_client")
@patch("app.services.citation_service.neo4j_service")
async def test_sync_paper_citations_success(mock_neo_service, mock_neo_client, mock_s2_client):
    mock_db = AsyncMock()
    mock_paper = MagicMock()
    mock_paper.semantic_scholar_id = "s2-test-id"
    mock_db.scalar.return_value = mock_paper
    
    mock_s2_client.get_citations_and_references = AsyncMock(return_value={
        "citations": [{"semantic_scholar_id": "c1", "title": "C1"}],
        "references": [{"semantic_scholar_id": "r1", "title": "R1"}]
    })
    
    mock_neo_sess = AsyncMock()
    mock_neo_client.get_session = AsyncMock(return_value=mock_neo_sess)
    mock_neo_service.add_citation = AsyncMock()
    
    # AsyncContextManager mock for async with
    mock_neo_sess.__aenter__.return_value = mock_neo_sess
    
    await citation_service.sync_paper_citations(mock_db, str(uuid.uuid4()))
    
    # Should run 2 queries for the 2 papers
    assert mock_neo_sess.run.call_count == 2
    
    # Should call add_citation twice (once for citation, once for reference)
    assert mock_neo_service.add_citation.call_count == 2
