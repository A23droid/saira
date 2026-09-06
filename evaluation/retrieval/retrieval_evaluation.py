"""
Retrieval evaluation: generate document-specific questions with known gold
chunks, then measure whether scoped retrieval finds them.

Question generation is grounded in a *specific chunk*: the model is shown one
chunk and asked for a question that only that passage answers. The chunk it was
generated from is therefore the gold label, established before retrieval runs
rather than judged afterwards. Questions the model cannot ground in the passage
are discarded instead of being scored.
"""

from __future__ import annotations

import asyncio
import logging
import random
from typing import Any, Dict, List, Optional

from evaluation.retrieval import retrieval_metrics

logger = logging.getLogger(__name__)

_QGEN_SYSTEM = (
    "You generate factual evaluation questions from a passage of a scientific "
    "paper.\n"
    "Given ONE passage, produce a question whose answer appears verbatim in "
    "that passage and is SPECIFIC to this paper — a number, a name, a dataset, "
    "a model, a metric, a hyperparameter, a result.\n"
    "Reject passages that are references, headers, or boilerplate by returning "
    '{"usable": false}.\n'
    "Do NOT ask questions answerable from general knowledge without the "
    "passage. Do NOT ask about 'the paper' generically.\n"
    'Return JSON: {"usable": true, "question": "...", "answer": "...", '
    '"answer_type": "number|name|dataset|metric|method|other"}\n'
    "The 'answer' must be copied verbatim from the passage."
)


async def fetch_chunks(paper_id: str, limit: int = 60) -> List[Dict[str, Any]]:
    from app.db.neo4j_client import neo4j_client
    sess = await neo4j_client.get_session()
    async with sess:
        return await (await sess.run(
            """
            MATCH (:Paper {id:$id})-[:HAS_CHUNK]->(c:Chunk)
            WHERE c.embedding IS NOT NULL AND size(c.text) > 400
            RETURN c.id AS id, c.text AS text, c.page AS page,
                   c.chunk_index AS chunk_index
            ORDER BY c.chunk_index
            LIMIT $limit
            """, id=paper_id, limit=limit)).data()


async def generate_facts(
    paper_id: str,
    n_facts: int = 8,
    seed: int = 13,
    trace=None,
) -> List[Dict[str, Any]]:
    """Produce (question, answer, gold_chunk) triples for one document."""
    from app.services.ai_router import _model_for
    from app.schemas.ai import AITask
    from app.services.groq_service import groq_service

    chunks = await fetch_chunks(paper_id)
    if not chunks:
        return []

    # Sample across the document (skip the first chunk: usually title/authors)
    rng = random.Random(seed)
    pool = chunks[1:] if len(chunks) > 1 else chunks
    rng.shuffle(pool)

    model = _model_for(AITask.LIT_REVIEW_PAPER)
    facts: List[Dict[str, Any]] = []
    consecutive_failures = 0

    for chunk in pool:
        if len(facts) >= n_facts:
            break
        text = (chunk["text"] or "")[:3000]
        try:
            data = await groq_service.chat_complete_json(
                model,
                [
                    {"role": "system", "content": _QGEN_SYSTEM},
                    {"role": "user", "content":
                        f"PASSAGE (page {chunk['page']}):\n{text}\n\nReturn JSON."},
                ],
                temperature=0.1,
                max_tokens=1200,
            )
        except Exception as exc:
            logger.warning("Question generation failed for %s: %s", chunk["id"], exc)
            consecutive_failures += 1
            if consecutive_failures >= 4:
                # Repeated provider failures: stop rather than burning the rest
                # of the pool and reporting the shortfall as a pipeline result.
                logger.error("Aborting question generation after %d consecutive "
                             "provider failures.", consecutive_failures)
                break
            continue
        consecutive_failures = 0

        if not data.get("usable"):
            continue
        question = str(data.get("question") or "").strip()
        answer = str(data.get("answer") or "").strip()
        if not question or not answer:
            continue
        # The stated answer must really be in the passage, otherwise the "gold"
        # label would be a model assertion rather than a property of the text.
        if answer.lower()[:60] not in text.lower():
            logger.info("Discarded question: answer not verbatim in passage.")
            continue

        fact = {
            "question": question,
            "answer": answer,
            "answer_type": data.get("answer_type"),
            "gold_chunk_id": chunk["id"],
            "gold_page": chunk["page"],
            "paper_id": paper_id,
        }
        facts.append(fact)
        if trace:
            trace.write("fact_generated", fact)

    return facts


async def evaluate_retrieval(
    db,
    document,
    facts: List[Dict[str, Any]],
    k_values: List[int],
    top_k: int = 10,
    trace=None,
) -> Dict[str, Any]:
    """Run scoped retrieval for each question and score it."""
    from app.services.retrieval_service import retrieval_service

    scope = await retrieval_service.resolve_paper_scope(db, document.paper_id)
    records: List[Dict[str, Any]] = []

    for fact in facts:
        result = await retrieval_service.retrieve(scope, fact["question"], top_k=top_k)
        retrieved_ids = [c.chunk_id for c in result.chunks]
        record = {
            "question": fact["question"],
            "expected_answer": fact["answer"],
            "relevant_chunk_ids": [fact["gold_chunk_id"]],
            "gold_page": fact["gold_page"],
            "retrieved_chunk_ids": retrieved_ids,
            "retrieved_pages": [c.page for c in result.chunks],
            "retrieved_paper_ids": sorted({c.paper_id for c in result.chunks}),
            "similarity_scores": [round(c.score, 6) for c in result.chunks],
            "candidate_count": result.candidate_count,
            "latency_ms": round(result.latency_ms, 2),
            "error": result.error,
            "scope_violation": any(
                c.paper_id != document.paper_id for c in result.chunks
            ),
        }
        records.append(record)
        if trace:
            trace.write("retrieval", {"paper_id": document.paper_id, **record})

    metrics = retrieval_metrics.aggregate(records, k_values)
    return {
        "document": document.to_dict(),
        "metrics": metrics,
        "records": records,
        "scope_violations": sum(1 for r in records if r["scope_violation"]),
    }
