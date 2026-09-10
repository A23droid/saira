"""
End-to-end paper ingestion.

    acquire PDF → compile knowledge → persist status

PDF acquisition is unchanged from the GraphRAG implementation: the URL is
resolved from a trusted identifier, validated before download, size-capped,
and magic-byte checked. That part was never graph-specific and it carries the
distinction the UI depends on — "we could not get the file"
(`pdf_unavailable`) versus "we got it and it broke" (`failed`).

What changed is everything after acquisition. Chunk → embed → Neo4j is gone;
the PDF now goes to `knowledge_compiler`, which extracts verbatim source
units, compiles an LLM-Wiki page, and writes both to the knowledge store and
the Postgres index. Concept extraction is part of that single compilation call
rather than a second LLM round trip.

The indexing state machine is unchanged, so the frontend's polling contract
(`GET /papers/{id}/indexing-status`, `ask_ai_ready`) still holds:

    not_indexed → queued → downloading_pdf → indexing → indexed
                                          ↘ pdf_unavailable   (acquisition)
                                          ↘ failed            (processing)
"""

import logging
from typing import Optional

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.paper import Paper
from app.services.knowledge_compiler import CompilationError, knowledge_compiler
from app.services.pdf_validator import pdf_validator

logger = logging.getLogger(__name__)

# Generous but finite: a research PDF above this is almost certainly not one.
_MAX_PDF_BYTES = 100 * 1024 * 1024


class PdfUnavailable(Exception):
    """The PDF could not be obtained — distinct from a processing failure."""


class ResearchIndexer:

    async def index_paper(
        self, db_session: AsyncSession, paper_id: str, force: bool = False
    ) -> None:
        import uuid

        stmt = select(Paper).where(Paper.id == uuid.UUID(str(paper_id)))
        paper = await db_session.scalar(stmt)
        if not paper:
            logger.error("Paper %s not found for indexing.", paper_id)
            return

        if paper.indexing_status == "indexed" and not force:
            logger.info("Paper %s is already indexed.", paper_id)
            return

        paper.indexing_error = None

        # ── 1. Acquire the PDF ────────────────────────────────────────────
        try:
            paper.indexing_status = "downloading_pdf"
            await db_session.commit()
            logger.info("pdf_download_started paper_id=%s", paper_id)

            pdf_url = await self._resolve_pdf_url(paper)
            if not pdf_url:
                raise PdfUnavailable("No accessible PDF source for this paper.")

            async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
                resp = await client.get(pdf_url)
                resp.raise_for_status()
                pdf_bytes = resp.content

            if not pdf_bytes.lstrip()[:5].startswith(b"%PDF-"):
                # Validation runs on a streamed probe; the full GET can still
                # land on an interstitial HTML page.
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

        # ── 2. Compile knowledge ──────────────────────────────────────────
        try:
            paper.indexing_status = "indexing"
            await db_session.commit()
            logger.info("knowledge_compilation_started paper_id=%s", paper_id)

            result = await knowledge_compiler.compile_paper(
                db_session, str(paper.id), pdf_bytes
            )

            # `compile_paper` commits the knowledge rows; re-read the paper so
            # the status write below is applied to a live instance.
            paper = await db_session.scalar(stmt)
            if paper is None:
                logger.error("Paper %s vanished mid-compilation.", paper_id)
                return

            paper.indexing_status = "indexed"
            # A degraded compilation still produced searchable source units, so
            # the paper is answerable — but say why the wiki page is thin
            # instead of reporting an unqualified success.
            paper.indexing_error = "; ".join(result.notes) if result.notes else None
            await db_session.commit()

            logger.info(
                "indexing_succeeded paper_id=%s source_units=%d compiled=%d "
                "verified=%d concepts=%d degraded=%s ask_ai_ready=true",
                paper_id, result.source_units, result.compiled_fields,
                result.verified_fields, result.concepts, result.degraded,
            )
        except CompilationError as e:
            # Text extraction failed — a scanned or encrypted PDF. The file was
            # obtained, so this is a processing failure, not an acquisition one.
            logger.warning("compilation_failed paper_id=%s error=%s", paper_id, e)
            await db_session.rollback()
            paper = await db_session.scalar(stmt)
            if paper:
                paper.indexing_status = "failed"
                paper.indexing_error = str(e)
                await db_session.commit()
        except Exception as e:
            logger.error("indexing_failed paper_id=%s error=%s", paper_id, e, exc_info=True)
            await db_session.rollback()
            paper = await db_session.scalar(stmt)
            if paper:
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


research_indexer = ResearchIndexer()
