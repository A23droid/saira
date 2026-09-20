import pytest
from app.services.document_parser import document_parser
from app.services.chunking_service import chunking_service

# Mock or basic tests for multimodal RAG components
# Full end-to-end requires Neo4j and a sample PDF.

def test_document_parser_handles_empty():
    elements = document_parser.parse(b"%PDF-1.4\n")
    # minimal dummy PDF
    assert isinstance(elements, list)

def test_chunking_service():
    elements = [
        {"type": "text", "page": 1, "text": "This is a simple text block.", "bbox": [0,0,100,100]},
        {"type": "table", "page": 1, "text": "Header1\tHeader2\nVal1\tVal2", "bbox": [100,100,200,200]},
        {"type": "caption", "page": 1, "text": "Table 1: Test", "associated_to": "table", "bbox": [200,200,300,300]}
    ]
    chunks = chunking_service.chunk_elements(elements)
    
    # Text chunk
    assert chunks[0]["type"] == "text"
    assert "simple text block" in chunks[0]["text"]
    
    # Table chunk
    assert chunks[1]["type"] == "table"
    assert "[TABLE]" in chunks[1]["text"]
    assert "Header1\tHeader2" in chunks[1]["text"]
    # Due to simplistic mock, just check it parses safely

# To run full evaluation:
# 1. Provide test_pdfs/
# 2. Ingest with new research_indexer
# 3. Query specific visual questions (e.g., "What does Table 1 say?")
# 4. Measure retrieval type distribution (text vs table vs figure)
