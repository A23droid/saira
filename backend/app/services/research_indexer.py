import asyncio
import logging
from typing import Dict, Any, List, Optional
import uuid

import fitz  # PyMuPDF
from sentence_transformers import SentenceTransformer

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.paper import Paper
from app.db.neo4j_client import neo4j_client
from app.services.neo4j_service import neo4j_service
from app.services.pdf_validator import pdf_validator
from app.services.concept_service import concept_service
from app.services.embedding_service import embedding_service

logger = logging.getLogger(__name__)

# Generous but finite: a research PDF above this is almost certainly not one.
_MAX_PDF_BYTES = 100 * 1024 * 1024


class PdfUnavailable(Exception):
    """The PDF could not be obtained — distinct from a processing failure."""


def _chunk_text(text: str, page_num: int, chunk_size: int = 500, overlap: int = 50) -> List[Dict[str, Any]]:
    """Simple word-based chunking."""
    words = text.split()
    chunks = []
    
    if not words:
        return chunks
        
    start = 0
    while start < len(words):
        end = start + chunk_size
        chunk_words = words[start:end]
        chunk_text = " ".join(chunk_words)
        
        chunks.append({
            "text": chunk_text,
            "page": page_num
        })
        
        start += (chunk_size - overlap)
        
    return chunks

class ResearchIndexer:
    async def index_paper(self, db_session: AsyncSession, paper_id: str, force: bool = False) -> None:
        """
        End-to-end background indexing pipeline for a paper.
        1. Fetch PDF
        2. Extract text & chunk
        3. Embed
        4. Store in Neo4j
        5. Trigger concept extraction on chunks
        """
        # Fetch paper and update status
        stmt = select(Paper).where(Paper.id == uuid.UUID(paper_id))
        paper = await db_session.scalar(stmt)
        if not paper:
            logger.error(f"Paper {paper_id} not found for indexing.")
            return

        if paper.indexing_status == "indexed" and not force:
            logger.info(f"Paper {paper_id} is already indexed.")
            return

        paper.indexing_error = None

        # ── 1. Acquire the PDF ────────────────────────────────────────────
        # PDF acquisition failure is reported separately from processing
        # failure: "we could not get the file" and "we got the file and it
        # broke" are different things to a user and to a retry.
        try:
            paper.indexing_status = "downloading_pdf"
            await db_session.commit()
            logger.info("pdf_download_started paper_id=%s", paper_id)

            pdf_url = await self._resolve_pdf_url(paper)
            if not pdf_url:
                raise PdfUnavailable("No accessible PDF source for this paper.")

            import httpx

            async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
                resp = await client.get(pdf_url)
                resp.raise_for_status()
                pdf_bytes = resp.content

            if not pdf_bytes.lstrip()[:5].startswith(b"%PDF-"):
                # Validation is done on a HEAD-ish streamed probe; the full GET
                # can still land on an interstitial HTML page.
                raise PdfUnavailable("Downloaded content is not a PDF.")
            if len(pdf_bytes) > _MAX_PDF_BYTES:
                raise PdfUnavailable(f"PDF exceeds size limit ({len(pdf_bytes)} bytes).")

            if pdf_url != paper.pdf_url:
                paper.pdf_url = pdf_url  # canonical source, resolved once
            logger.info("pdf_download_succeeded paper_id=%s bytes=%d", paper_id, len(pdf_bytes))
        except Exception as e:
            reason = str(e)
            logger.warning("pdf_download_failed paper_id=%s error=%s", paper_id, reason)
            paper.indexing_status = "pdf_unavailable"
            paper.indexing_error = reason
            await db_session.commit()
            return

        try:
            paper.indexing_status = "indexing"
            await db_session.commit()
            logger.info("indexing_started paper_id=%s", paper_id)

            # 3. Extract Text & Chunk (Run in executor to avoid blocking event loop)
            chunks = await asyncio.to_thread(self._extract_and_chunk, pdf_bytes)
            
            if not chunks:
                raise ValueError("No extractable text found in PDF.")

            # 4. Generate Embeddings (Run in executor)
            embeddings = await asyncio.to_thread(self._embed_chunks, [c["text"] for c in chunks])
            
            for i, chunk in enumerate(chunks):
                chunk["chunk_index"] = i
                chunk["embedding"] = embeddings[i]
                chunk["id"] = f"{paper_id}_chunk_{i}"

            # 5. Store in Neo4j (idempotent: stale chunks from a previous,
            #    longer extraction are removed so a re-index replaces rather
            #    than accumulates).
            await self._store_chunks_in_neo4j(
                str(paper.id), chunks,
                paper_meta={
                    "title": paper.title,
                    "publication_year": paper.publication_year,
                    "doi": paper.doi,
                    "arxiv_id": paper.arxiv_id,
                    "semantic_scholar_id": paper.semantic_scholar_id,
                },
            )

            # 6. Extract Concepts using the new context
            # (Passing the db_session to the existing concept service, but it might need updating 
            # to use chunks instead of just the abstract. For now, we trigger it.)
            # Wait, concept_service uses db_paper. We will modify concept_service later if needed.
            await concept_service.sync_paper_concepts(db_session, str(paper.id))

            # Mark complete
            paper.indexing_status = "indexed"
            paper.indexing_error = None
            await db_session.commit()
            logger.info(
                "indexing_succeeded paper_id=%s chunks=%d ask_ai_ready=true",
                paper_id, len(chunks),
            )

        except Exception as e:
            logger.error("indexing_failed paper_id=%s error=%s", paper_id, e, exc_info=True)
            paper.indexing_status = "failed"
            paper.indexing_error = str(e)
            await db_session.commit()

    async def _resolve_pdf_url(self, paper: Paper) -> Optional[str]:
        """Pick a canonical PDF URL for this paper and prove it is a PDF.

        Priority: the stored URL, then a URL derived from a trusted repository
        identifier. Candidates are never downloaded blindly — each one is
        validated (status, content type, %PDF- magic bytes) first.
        """
        candidates = [paper.pdf_url]
        if paper.arxiv_id:
            arxiv_id = paper.arxiv_id.split("/")[-1].replace("arXiv:", "").strip()
            if arxiv_id:
                candidates.append(f"https://arxiv.org/pdf/{arxiv_id}")
        return await pdf_validator.find_valid_pdf([c for c in candidates if c])

    def _extract_and_chunk(self, pdf_bytes: bytes) -> List[Dict[str, Any]]:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        all_chunks = []
        
        for page_num in range(len(doc)):
            page = doc[page_num]
            text = page.get_text("text").strip()
            if text:
                page_chunks = _chunk_text(text, page_num + 1)
                all_chunks.extend(page_chunks)
                
        doc.close()
        return all_chunks

    def _embed_chunks(self, texts: List[str]) -> Any:
        return embedding_service.embed_texts(texts)

    async def _store_chunks_in_neo4j(
        self,
        paper_id: str,
        chunks: List[Dict[str, Any]],
        paper_meta: Optional[Dict[str, Any]] = None,
    ) -> None:
        neo_sess = await neo4j_client.get_session()
        
        index_query = """
        CREATE VECTOR INDEX chunk_embeddings IF NOT EXISTS
        FOR (c:Chunk)
        ON (c.embedding)
        OPTIONS { indexConfig: {
         `vector.dimensions`: 384,
         `vector.similarity_function`: 'cosine'
        }}
        """
        
        # Carry real metadata onto the Paper node. A bare `MERGE (p:Paper
        # {id})` used to create title-less nodes whenever indexing ran before
        # the metadata upsert, leaving the graph full of anonymous papers.
        meta_query = """
        MERGE (p:Paper {id: $paper_id})
        SET p.title               = coalesce($title, p.title),
            p.publication_year    = coalesce($publication_year, p.publication_year),
            p.doi                 = coalesce($doi, p.doi),
            p.arxiv_id            = coalesce($arxiv_id, p.arxiv_id),
            p.semantic_scholar_id = coalesce($semantic_scholar_id, p.semantic_scholar_id)
        """

        # Remove chunks that are no longer produced by the current extraction.
        # Without this, re-indexing a paper whose text got shorter leaves
        # orphaned chunks that still match vector search.
        prune_query = """
        MATCH (p:Paper {id: $paper_id})-[:HAS_CHUNK]->(c:Chunk)
        WHERE NOT c.id IN $chunk_ids
        DETACH DELETE c
        """

        query = """
        MERGE (p:Paper {id: $paper_id})
        WITH p
        UNWIND $chunks AS chunk_data
        MERGE (c:Chunk {id: chunk_data.id})
        SET c.text = chunk_data.text,
            c.page = chunk_data.page,
            c.chunk_index = chunk_data.chunk_index,
            c.paper_id = $paper_id
        MERGE (p)-[:HAS_CHUNK]->(c)
        """
        
        async with neo_sess:
            # First create the vector index if it doesn't exist
            try:
                await neo_sess.run(index_query)
            except Exception as e:
                logger.warning(f"Vector index creation failed (may already exist or syntax error): {e}")
            
            meta = paper_meta or {}
            await neo_sess.run(
                meta_query,
                paper_id=paper_id,
                title=meta.get("title"),
                publication_year=meta.get("publication_year"),
                doi=meta.get("doi"),
                arxiv_id=meta.get("arxiv_id"),
                semantic_scholar_id=meta.get("semantic_scholar_id"),
            )

            await neo_sess.run(
                prune_query, paper_id=paper_id,
                chunk_ids=[c["id"] for c in chunks],
            )

            # Then insert basic properties and relationships
            await neo_sess.run(query, paper_id=paper_id, chunks=chunks)
            
            # Then set embeddings
            set_vec_query = """
            UNWIND $chunks AS chunk_data
            MATCH (c:Chunk {id: chunk_data.id})
            CALL db.create.setNodeVectorProperty(c, 'embedding', chunk_data.embedding)
            """
            
            try:
                await neo_sess.run(set_vec_query, chunks=chunks)
            except Exception as e:
                logger.warning(f"setNodeVectorProperty failed: {e}. Falling back to regular SET.")
                # Fallback if setNodeVectorProperty fails
                fallback_query = """
                UNWIND $chunks AS chunk_data
                MATCH (c:Chunk {id: chunk_data.id})
                SET c.embedding = chunk_data.embedding
                """
                await neo_sess.run(fallback_query, chunks=chunks)

research_indexer = ResearchIndexer()
