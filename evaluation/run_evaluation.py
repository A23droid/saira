"""
SAIRA evaluation orchestrator.

    python -m evaluation.run_evaluation                # full run
    python -m evaluation.run_evaluation --retrieval-only
    python -m evaluation.run_evaluation --skip-graph
    python -m evaluation.run_evaluation --questions 4

Produces, in evaluation/reports/:
    <run_id>-results.json     every measurement from this run
    <run_id>-report.md        human-readable report
    traces/<run_id>-*.jsonl   per-step traces (retrieval, prompts, graph writes)

Nothing in the output is hardcoded — every number is computed from the run.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from typing import Any, Dict, List

from evaluation.common.bootstrap import TraceWriter, bootstrap, new_run_id, utcnow

bootstrap()  # must run before any `app.*` import so eval mode is in effect

from evaluation.common import reporting  # noqa: E402
from evaluation.concept_graph import graph_evaluation, graph_metrics  # noqa: E402
from evaluation.config.evaluation_config import load_config  # noqa: E402
from evaluation.discovery import document_discovery  # noqa: E402
from evaluation.grounding import causal_tests, context_tests, grounding_metrics  # noqa: E402
from evaluation.ingestion import evaluation_ingestion  # noqa: E402
from evaluation.leakage import leakage_checks  # noqa: E402
from evaluation.retrieval import retrieval_evaluation  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
for noisy in ("httpx", "neo4j", "sentence_transformers", "urllib3",
              "app.services.groq_service"):
    logging.getLogger(noisy).setLevel(logging.WARNING)
log = logging.getLogger("evaluation")


async def main(args) -> int:
    from app.db.neo4j_client import neo4j_client
    from app.db.session import AsyncSessionLocal
    from evaluation.common import throttle

    # Pace LLM calls to the provider's tokens-per-minute ceiling. Timing only:
    # prompts, model, and parameters are unchanged.
    throttle.install(args.tpm)

    cfg = load_config(max_questions_per_document=args.questions)
    run_id = new_run_id()
    cfg.run_id = run_id
    trace = TraceWriter(run_id, "trace", cfg.traces_dir)

    results: Dict[str, Any] = {
        "run_id": run_id,
        "started_at": utcnow(),
        "config": cfg.to_dict(),
        "phases": {},
    }

    log.info("=== SAIRA evaluation run %s ===", run_id)
    await neo4j_client.connect()

    async with AsyncSessionLocal() as db:
        # ── Phase 1: discovery ────────────────────────────────────────────────
        log.info("[1/7] Discovering evaluation documents...")
        docs = await document_discovery.select_documents(
            db,
            queries=cfg.discovery_queries,
            candidates_per_query=cfg.discovery_candidates_per_query,
            min_chunks=cfg.min_chunks_required,
            needed=2,
            allow_existing=True,
        )
        results["phases"]["discovery"] = {
            "documents": [d.to_dict() for d in docs],
            "count": len(docs),
        }
        if not docs:
            results["fatal"] = "No evaluation documents could be discovered or reused."
            reporting.write_json(f"{run_id}-results.json", results, cfg.reports_dir)
            log.error(results["fatal"])
            return 1
        for d in docs:
            log.info("   [%s] %s (%d chunks)", d.source, d.title[:60], d.chunk_count)

        # ── Phase 2: ingestion integrity ──────────────────────────────────────
        log.info("[2/7] Verifying ingestion integrity...")
        ingestion = [await evaluation_ingestion.verify_ingestion(d.paper_id) for d in docs]
        for r in ingestion:
            trace.write("ingestion_verification", r)
            log.info("   %s: %s", r["paper_id"][:8],
                     "OK" if r["all_passed"] else f"FAILED {r['failed_checks']}")
        results["phases"]["ingestion"] = ingestion

        # ── Phase 3: leakage audit ────────────────────────────────────────────
        log.info("[3/7] Running leakage audit...")
        results["phases"]["leakage"] = leakage_checks.run_audit()
        log.info("   findings: %s",
                 results["phases"]["leakage"]["counts_by_severity"])

        # ── Phase 4: retrieval ────────────────────────────────────────────────
        log.info("[4/7] Generating questions and evaluating retrieval...")
        retrieval_reports, all_facts = [], {}
        for d in docs:
            facts = await retrieval_evaluation.generate_facts(
                d.paper_id, n_facts=cfg.max_questions_per_document, trace=trace)
            all_facts[d.paper_id] = facts
            log.info("   %s: %d questions", d.title[:45], len(facts))
            if not facts:
                continue
            rep = await retrieval_evaluation.evaluate_retrieval(
                db, d, facts, cfg.retrieval_k_values, cfg.retrieval_top_k, trace)
            retrieval_reports.append(rep)
            m = rep["metrics"]
            log.info("      hit@1=%s hit@5=%s mrr=%s violations=%d",
                     m.get("hit@1"), m.get("hit@5"), m.get("mrr"),
                     rep["scope_violations"])
        results["phases"]["retrieval"] = retrieval_reports

        if args.retrieval_only:
            results["finished_at"] = utcnow()
            _finalize(results, cfg, run_id)
            return 0

        # ── Phase 5: causal grounding tests ───────────────────────────────────
        log.info("[5/7] Running causal grounding tests (A-F)...")
        runner = causal_tests.CausalTestRunner(db, cfg, trace)
        causal_records: List[Dict[str, Any]] = []
        primary = docs[0]
        wrong_doc = docs[1] if len(docs) > 1 else None
        for fact in all_facts.get(primary.paper_id, [])[:cfg.max_questions_per_document]:
            try:
                causal_records.extend(await runner.run_for_fact(primary, fact, wrong_doc))
            except Exception as exc:
                log.error("   causal test failed for %r: %s", fact["question"][:50], exc)
                causal_records.append({
                    "test": "A_correct_context", "question": fact["question"],
                    "passed": False, "verdict": "GENERATION_FAILURE",
                    "error": str(exc),
                })
        results["phases"]["causal"] = causal_records
        log.info("   %d causal records", len(causal_records))

        # ── Phase 6: document switch (G-J) ────────────────────────────────────
        log.info("[6/7] Constructing conflicting document switch...")
        switch_records: List[Dict[str, Any]] = []
        conflict = None
        if len(docs) >= 2:
            conflict = await context_tests.find_conflicting_question(
                docs[0], docs[1], trace=trace)
        if conflict:
            log.info("   conflict found: %r | A=%r B=%r",
                     conflict["question"][:60], conflict["answer_a"], conflict["answer_b"])
            switch_records = await context_tests.run_document_switch(
                db, docs[0], docs[1], conflict, trace)
            for r in switch_records:
                log.info("      %s -> %s", r["test"], r["verdict"])
        else:
            reason = ("No question was found that both documents answer with "
                      "different specific values.")
            log.warning("   %s Reporting NOT_SATISFIED.", reason)
            switch_records = context_tests.not_satisfied_records(reason)
        results["phases"]["document_switch"] = {
            "conflict": conflict, "records": switch_records,
        }

        # ── Phase 7: concept graph ────────────────────────────────────────────
        if not args.skip_graph:
            log.info("[7/7] Evaluating concept graph...")
            build = await graph_evaluation.build_graphs(db, docs, trace)
            for b in build:
                log.info("   %s: concepts=%d relations=%d err=%s",
                         b["paper_id"][:8], b["concepts"], b["relations"], b["error"])
            measured = await graph_evaluation.measure(docs, trace)
            isolation = await graph_evaluation.test_isolation(docs, trace)
            idem = await graph_evaluation.test_reingestion_idempotency(db, docs[0], trace)
            api = await graph_evaluation.test_graph_api(db, docs, trace)
            verdict = graph_metrics.graph_verdict(
                measured,
                isolation_ok=bool(isolation.get("passed", False)) or not isolation.get("applicable", True),
                idempotent=bool(idem.get("passed")),
                api_ok=bool(api.get("passed")),
                extraction_reports=build,
            )
            results["phases"]["concept_graph"] = {
                "extraction": build, "metrics": measured,
                "isolation": isolation, "idempotency": idem,
                "api": api, "verdict": verdict,
            }
            log.info("   concept graph verdict: %s", verdict["verdict"])
        else:
            results["phases"]["concept_graph"] = {"skipped": True}

    await neo4j_client.close()

    # ── Aggregate verdicts ────────────────────────────────────────────────────
    causal_summary = grounding_metrics.summarize_causal(results["phases"]["causal"])
    influence = grounding_metrics.context_influence(results["phases"]["causal"])
    leak = grounding_metrics.leakage_signals(results["phases"]["causal"])
    cites = grounding_metrics.citation_metrics(results["phases"]["causal"])
    rag_verdict = grounding_metrics.overall_verdict(
        causal_summary, results["phases"]["document_switch"]["records"], influence, leak)

    results["summary"] = {
        "causal_by_test": causal_summary,
        "context_influence": influence,
        "leakage_signals": leak,
        "citation_metrics": cites,
        "rag_verdict": rag_verdict,
        "concept_graph_verdict":
            results["phases"]["concept_graph"].get("verdict", {"verdict": "SKIPPED"}),
    }
    results["finished_at"] = utcnow()
    _finalize(results, cfg, run_id)
    log.info("RAG verdict: %s", rag_verdict["verdict"])
    return 0


def _finalize(results, cfg, run_id) -> None:
    from evaluation.reports_builder import build_markdown
    json_path = reporting.write_json(f"{run_id}-results.json", results, cfg.reports_dir)
    md_path = reporting.write_text(
        f"{run_id}-report.md", build_markdown(results), cfg.reports_dir)
    reporting.write_text("LATEST.md", build_markdown(results), cfg.reports_dir)
    log.info("Wrote %s", json_path.name)
    log.info("Wrote %s (and LATEST.md)", md_path.name)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Run the SAIRA evaluation harness.")
    p.add_argument("--retrieval-only", action="store_true",
                   help="Stop after retrieval metrics (no generation calls).")
    p.add_argument("--skip-graph", action="store_true",
                   help="Skip concept-graph evaluation.")
    p.add_argument("--questions", type=int, default=None,
                   help="Questions generated per document.")
    p.add_argument("--tpm", type=int, default=8000,
                   help="Provider tokens-per-minute ceiling used for pacing.")
    args = p.parse_args()
    sys.exit(asyncio.run(main(args)))
