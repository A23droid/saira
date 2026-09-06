"""Render a run's results dict as Markdown. Pure formatting — no computation."""

from __future__ import annotations

from typing import Any, Dict, List

from evaluation.common.reporting import md_table


def build_markdown(r: Dict[str, Any]) -> str:
    ph = r.get("phases", {})
    s = r.get("summary", {})
    out: List[str] = [
        f"# SAIRA Evaluation Report",
        "",
        f"**Run ID:** `{r.get('run_id')}`  ",
        f"**Started:** {r.get('started_at')}  ",
        f"**Finished:** {r.get('finished_at', 'n/a')}",
        "",
        "All numbers below are computed from this run. Nothing is hardcoded.",
        "",
    ]

    if r.get("fatal"):
        out += ["## FATAL", "", f"> {r['fatal']}", ""]
        return "\n".join(out)

    # -- Verdicts --------------------------------------------------------------
    rag = s.get("rag_verdict", {})
    cg = s.get("concept_graph_verdict", {})
    out += [
        "## Verdicts", "",
        f"- **RAG:** `{rag.get('verdict', 'n/a')}`",
        f"- **Concept Graph:** `{cg.get('verdict', 'n/a')}`",
        "",
    ]
    if rag.get("limiting_factors"):
        out += ["**RAG limiting factors:**", ""]
        out += [f"- {x}" for x in rag["limiting_factors"]] + [""]
    if cg.get("limiting_factors"):
        out += ["**Concept graph limiting factors:**", ""]
        out += [f"- {x}" for x in cg["limiting_factors"]] + [""]
    if rag.get("interpretation"):
        out += [f"> {rag['interpretation']}", ""]

    # -- Corpus ----------------------------------------------------------------
    docs = ph.get("discovery", {}).get("documents", [])
    if docs:
        out += ["## Evaluation corpus", "",
                md_table(["paper_id", "title", "chunks", "source"],
                         [[d["paper_id"][:8], (d["title"] or "")[:58],
                           d["chunk_count"], d["source"]] for d in docs]), ""]

    # -- Ingestion -------------------------------------------------------------
    ing = ph.get("ingestion", [])
    if ing:
        out += ["## Ingestion integrity", "",
                md_table(["paper", "chunks", "pages", "dims", "dup text",
                          "cross-doc", "result"],
                         [[i["paper_id"][:8], i["chunk_count"], i["distinct_pages"],
                           i["embedding_dims"], i["duplicate_text_chunks"],
                           i["cross_document_chunks"],
                           "PASS" if i["all_passed"] else "FAIL: " + ", ".join(i["failed_checks"])]
                          for i in ing]), ""]

    # -- Retrieval -------------------------------------------------------------
    ret = ph.get("retrieval", [])
    if ret:
        out += ["## Retrieval metrics", ""]
        rows = []
        for rep in ret:
            m = rep["metrics"]
            rows.append([
                rep["document"]["paper_id"][:8],
                m.get("questions_scored"),
                m.get("hit@1"), m.get("hit@3"), m.get("hit@5"),
                m.get("recall@5"), m.get("mrr"),
                round(m.get("latency_ms_mean", 0), 1),
                rep["scope_violations"],
            ])
        out += [md_table(["paper", "n", "Hit@1", "Hit@3", "Hit@5",
                          "Recall@5", "MRR", "latency ms", "scope viol."], rows), ""]

        out += ["### Representative retrievals", ""]
        for rep in ret[:1]:
            for rec in rep["records"][:3]:
                out += [
                    f"**Q:** {rec['question']}  ",
                    f"**Expected:** `{rec['expected_answer'][:100]}`  ",
                    f"**Gold chunk:** `{rec['relevant_chunk_ids'][0][-22:]}` (page {rec['gold_page']})  ",
                    f"**Retrieved:** " + ", ".join(
                        f"`{c[-22:]}`({sc:.3f})" for c, sc in
                        zip(rec["retrieved_chunk_ids"][:5], rec["similarity_scores"][:5])),
                    "", ]

    # -- Causal ----------------------------------------------------------------
    causal = s.get("causal_by_test", {})
    if causal:
        out += ["## Causal test results (A-F)", "",
                md_table(["test", "total", "passed", "failed", "n/a", "pass rate", "verdicts"],
                         [[t, b["total"], b["passed"], b["failed"], b["not_applicable"],
                           b["pass_rate"], ", ".join(f"{k}:{v}" for k, v in b["verdicts"].items())]
                          for t, b in sorted(causal.items())]), ""]

    ci = s.get("context_influence", {})
    if ci:
        out += ["### Context influence (perturbation)", "",
                f"- applicable cases: {ci.get('applicable')}",
                f"- followed the perturbed value: {ci.get('followed_perturbation')}",
                f"- kept the original value: {ci.get('kept_original_value')}",
                f"- follow rate: {ci.get('followed_perturbation_rate')}", ""]

    lk = s.get("leakage_signals", {})
    if lk:
        out += ["### Prior-knowledge / leakage signals", "",
                f"- no-context correct abstentions: "
                f"{lk.get('no_context_correct_abstentions')}/{lk.get('no_context_total')}",
                f"- answered correctly with NO evidence (prior knowledge): "
                f"{lk.get('no_context_answered_from_prior_knowledge')}",
                f"- wrong-context coincidental overlap (test artifacts): "
                f"{lk.get('wrong_context_coincidental_overlap')}",
                f"- wrong-context answered target anyway: "
                f"{lk.get('wrong_context_answered_target_anyway')}", ""]

    cm = s.get("citation_metrics", {})
    if cm:
        out += ["### Citation accuracy", "",
                f"- citations emitted: {cm.get('citations_total')}",
                f"- traceable to supplied evidence: {cm.get('citations_traceable_to_evidence')}",
                f"- fabricated (dropped by validator): {cm.get('fabricated_citations')}",
                f"- citation accuracy: {cm.get('citation_accuracy')}", ""]

    # -- Document switch -------------------------------------------------------
    ds = ph.get("document_switch", {})
    if ds:
        out += ["## Document-switch tests (G-J)", ""]
        conflict = ds.get("conflict")
        if conflict:
            out += [f"**Conflicting question:** {conflict['question']}  ",
                    f"**Document A answer:** `{conflict['answer_a']}`  ",
                    f"**Document B answer:** `{conflict['answer_b']}`", "",
                    md_table(["test", "expected", "actual (truncated)", "own", "other", "verdict"],
                             [[x["test"], x.get("expected"),
                               (x.get("actual") or "")[:70].replace("\n", " "),
                               x.get("matched_own_document"),
                               x.get("matched_other_document"), x["verdict"]]
                              for x in ds["records"]]), ""]
        else:
            out += ["> **NOT SATISFIED** — no genuinely conflicting question was found.",
                    "> An answer/abstain pair is deliberately NOT counted as a document switch.",
                    ""]
            for x in ds["records"][:1]:
                out += [f"> Reason: {x.get('reason')}", ""]

    # -- Concept graph ---------------------------------------------------------
    g = ph.get("concept_graph", {})
    if g and not g.get("skipped"):
        out += ["## Concept graph", ""]
        mets = g.get("metrics", [])
        if mets:
            out += [md_table(["paper", "concepts", "relations", "dup after norm",
                              "prov (chunks)", "prov (evidence)", "dangling", "classification"],
                             [[m["paper_id"][:8], m["concept_count"], m["relation_count"],
                               m["duplicate_after_normalization"],
                               m["provenance_coverage_chunks"],
                               m["provenance_coverage_evidence"],
                               m["dangling_relations"], ", ".join(m["classification"])]
                              for m in mets]), ""]
            out += ["### Representative concepts and relations", ""]
            for m in mets[:1]:
                for c in m["sample_concepts"][:6]:
                    out += [f"- `{c['name']}` (importance {c['importance']}, "
                            f"pages {c['pages']}, {c['chunks']} chunk(s))"]
                out += [""]
                for rel in m["sample_relations"][:6]:
                    out += [f"- `{rel['source']}` --**{rel['type']}**--> `{rel['target']}`"]
                out += [""]

        iso = g.get("isolation", {})
        if iso.get("applicable"):
            out += ["### Isolation", "",
                    f"- Paper A concepts: {iso['a_concepts']}, Paper B: {iso['b_concepts']}",
                    f"- graphs distinct: {iso['graphs_are_distinct']}",
                    f"- every A concept has an A edge: {iso['all_a_concepts_have_a_edge']}",
                    f"- foreign relations visible in A: {iso['foreign_relations_visible_in_a']}",
                    f"- shared concept names ({iso['shared_count']}): "
                    f"{', '.join(iso['shared_concept_names'][:8]) or 'none'}",
                    f"- **{iso['classification']}**", "",
                    f"> {iso['note']}", ""]

        idem = g.get("idempotency", {})
        if idem:
            out += ["### Re-ingestion idempotency", "",
                    f"- identical-payload replay idempotent: "
                    f"{idem.get('deterministic_replay_idempotent')}",
                    f"- no uncontrolled growth after full re-extraction: "
                    f"{idem.get('no_uncontrolled_growth')}",
                    f"- orphan concepts after: {idem.get('orphans_after')}",
                    f"- before: {idem.get('before')}",
                    f"- after replay: {idem.get('after_identical_replay')}",
                    f"- after re-extraction: {idem.get('after_full_reextraction')}",
                    f"- **{idem.get('classification')}**", "",
                    f"> {idem.get('note')}", ""]

        api = g.get("api", {})
        if api:
            out += ["### Graph API", "",
                    f"- paper API: {api['paper_api']}",
                    f"- project API: {api.get('project_api')}",
                    f"- **{api.get('classification')}**", ""]

    # -- Leakage ---------------------------------------------------------------
    lkg = ph.get("leakage", {})
    if lkg:
        out += ["## Static leakage audit", "",
                f"Counts by severity: `{lkg.get('counts_by_severity')}`", ""]
        high = [f for f in lkg.get("findings", []) if f["severity"] == "high"]
        if high:
            out += [md_table(["file", "line", "category", "snippet"],
                             [[f["file"], f["line"], f["category"], f["snippet"][:70]]
                              for f in high[:20]]), ""]
        else:
            out += ["No high-severity findings.", ""]
        out += ["### Runtime checks", "",
                md_table(["check", "passed", "detail"],
                         [[c["check"], c["passed"], c["detail"]]
                          for c in lkg.get("runtime_checks", [])]), ""]
        out += [f"> {lkg.get('note')}", ""]

    return "\n".join(out)
