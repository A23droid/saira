import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.knowledge import PaperCitation
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
async def test_sync_paper_citations_success(mock_s2_client):
    """Citation edges are staged into Postgres, one per external work.

    Rewritten for the LLM-Wiki migration: the Neo4j MERGE + `add_citation`
    pair became `PaperCitation` rows, so the assertion moved from "two Cypher
    statements ran" to "two rows were added, with the right directions".
    """
    mock_db = AsyncMock()
    mock_paper = MagicMock()
    mock_paper.id = uuid.uuid4()
    mock_paper.semantic_scholar_id = "s2-test-id"
    mock_db.scalar.return_value = mock_paper
    mock_db.add = MagicMock()

    mock_s2_client.get_citations_and_references = AsyncMock(return_value={
        "citations": [{"semantic_scholar_id": "c1", "title": "C1"}],
        "references": [{"semantic_scholar_id": "r1", "title": "R1"}],
    })

    await citation_service.sync_paper_citations(mock_db, str(uuid.uuid4()))

    added = [call.args[0] for call in mock_db.add.call_args_list]
    assert len(added) == 2, "expected one row per external work"
    assert all(isinstance(row, PaperCitation) for row in added)

    by_direction = {row.direction: row for row in added}
    # `references` are works this paper cites; `citations` are works citing it.
    # The naming is inherited from the Neo4j implementation and preserved.
    assert by_direction["outbound"].other_title == "R1"
    assert by_direction["inbound"].other_title == "C1"
    mock_db.commit.assert_awaited()


@pytest.mark.asyncio
@patch("app.services.citation_service.semantic_scholar_client")
async def test_external_work_without_an_id_is_skipped(mock_s2_client):
    """An edge with no stable identifier cannot be deduplicated on a re-sync,
    and a duplicated citation is worse than a missing one."""
    mock_db = AsyncMock()
    mock_paper = MagicMock()
    mock_paper.id = uuid.uuid4()
    mock_paper.semantic_scholar_id = "s2-test-id"
    mock_db.scalar.return_value = mock_paper
    mock_db.add = MagicMock()

    mock_s2_client.get_citations_and_references = AsyncMock(return_value={
        "citations": [{"title": "no id at all"}],
        "references": [{"semantic_scholar_id": "r1", "title": "R1"}],
    })

    await citation_service.sync_paper_citations(mock_db, str(uuid.uuid4()))

    added = [call.args[0] for call in mock_db.add.call_args_list]
    assert len(added) == 1
    assert added[0].other_semantic_scholar_id == "r1"
