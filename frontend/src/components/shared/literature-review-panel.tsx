"use client";

import { useCallback, useEffect, useState } from "react";
import { Sparkles, Copy, Download, RefreshCw, Check, AlertTriangle, ChevronDown, ChevronUp, ExternalLink } from "lucide-react";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { EmptyState } from "@/components/shared/empty-state";
import {
  getLitReview,
  generateLitReview,
  regenerateLitReview,
  LiteratureReviewResponse,
  LitReviewTheme,
  LitReviewReference,
} from "@/lib/api/project_ai";

// ── Section helpers ────────────────────────────────────────────────────────────

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  const [open, setOpen] = useState(true);
  return (
    <div className="border-b border-line-soft pb-5 last:border-0">
      <button
        onClick={() => setOpen((v) => !v)}
        className="mb-3 flex w-full items-center justify-between text-left"
      >
        <h3 className="font-display text-[0.95rem] font-semibold text-ink">{title}</h3>
        {open ? <ChevronUp className="h-4 w-4 text-ink-faint" /> : <ChevronDown className="h-4 w-4 text-ink-faint" />}
      </button>
      {open && children}
    </div>
  );
}

function BulletList({ items }: { items: string[] }) {
  if (!items || items.length === 0) return <p className="text-sm text-ink-faint italic">None identified.</p>;
  return (
    <ul className="space-y-1.5">
      {items.map((item, i) => (
        <li key={i} className="flex gap-2 text-sm text-ink-soft leading-relaxed">
          <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-teal-500" />
          {item}
        </li>
      ))}
    </ul>
  );
}

function ThemeCard({ theme, idx }: { theme: LitReviewTheme; idx: number }) {
  return (
    <div className="rounded-xl border border-line bg-paper-dim/30 p-4">
      <p className="mb-1.5 text-xs font-semibold uppercase tracking-wider text-teal-600">
        Theme {idx + 1}
      </p>
      <h4 className="mb-2 font-display text-sm font-semibold text-ink">{theme.title}</h4>
      <p className="text-sm text-ink-soft leading-relaxed">{theme.summary}</p>
      {theme.paper_ids && theme.paper_ids.length > 0 && (
        <p className="mt-2 text-xs text-ink-faint">
          Based on {theme.paper_ids.length} paper{theme.paper_ids.length !== 1 ? "s" : ""}
        </p>
      )}
    </div>
  );
}

function ReferenceItem({ ref: r, idx }: { ref: LitReviewReference; idx: number }) {
  return (
    <Link
      href={`/papers/${r.paper_id}`}
      className="group flex items-start gap-3 rounded-lg border border-line bg-surface px-3 py-2.5 hover:border-teal-400 transition-colors"
    >
      <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-teal-50 text-[10px] font-bold text-teal-600">
        {idx + 1}
      </span>
      <div className="min-w-0 flex-1">
        <p className="line-clamp-1 text-sm font-medium text-ink group-hover:text-teal-700">{r.title}</p>
        {(r.authors || r.year) && (
          <p className="text-xs text-ink-faint">
            {r.authors && <span>{r.authors}</span>}
            {r.authors && r.year && <span> · </span>}
            {r.year && <span>{r.year}</span>}
          </p>
        )}
      </div>
      <ExternalLink className="mt-0.5 h-3.5 w-3.5 shrink-0 text-ink-faint opacity-0 group-hover:opacity-100 transition-opacity" />
    </Link>
  );
}

// ── Main Component ─────────────────────────────────────────────────────────────

export function LiteratureReviewPanel({
  projectId,
  paperCount,
}: {
  projectId: string;
  paperCount: number;
}) {
  const [status, setStatus] = useState<"idle" | "loading" | "generating" | "done" | "error">("loading");
  const [review, setReview] = useState<LiteratureReviewResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  const loadExisting = useCallback(async () => {
    if (!projectId) return;
    try {
      const existing = await getLitReview(projectId);
      if (existing) {
        setReview(existing);
        setStatus("done");
      } else {
        setStatus("idle");
      }
    } catch (err) {
      console.error("Failed to load review:", err);
      setStatus("idle");
    }
  }, [projectId]);

  useEffect(() => {
    loadExisting();
  }, [loadExisting]);

  async function generate(isRegen = false) {
    setStatus("generating");
    setError(null);
    try {
      const result = isRegen
        ? await regenerateLitReview(projectId)
        : await generateLitReview(projectId);
      setReview(result);
      setStatus("done");
    } catch (err: any) {
      setError(err?.message ?? "Failed to generate the review. Please try again.");
      setStatus("error");
    }
  }

  function copy() {
    if (!review) return;
    const c = review.content;
    const text = [
      `# ${c.title}`,
      "",
      "## Overview",
      c.overview,
      "",
      ...(c.themes.length > 0
        ? ["## Themes", ...c.themes.map((t) => `### ${t.title}\n${t.summary}`), ""]
        : []),
      ...(c.key_findings.length > 0 ? ["## Key Findings", ...c.key_findings.map((f) => `- ${f}`), ""] : []),
      ...(c.research_gaps.length > 0 ? ["## Research Gaps", ...c.research_gaps.map((g) => `- ${g}`), ""] : []),
      ...(c.future_directions.length > 0 ? ["## Future Directions", ...c.future_directions.map((d) => `- ${d}`), ""] : []),
      ...(c.references.length > 0
        ? ["## References", ...c.references.map((r, i) => `[${i + 1}] ${r.title}${r.authors ? ` — ${r.authors}` : ""}${r.year ? ` (${r.year})` : ""}`)]
        : []),
    ].join("\n");
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }

  function exportMd() {
    if (!review) return;
    const c = review.content;
    const lines = [
      `# ${c.title}`,
      "",
      "## Overview",
      c.overview,
      "",
      ...(c.themes.length > 0
        ? ["## Themes", ...c.themes.flatMap((t) => [`### ${t.title}`, t.summary, ""]), ""]
        : []),
      ...(c.methodological_trends.length > 0 ? ["## Methodological Trends", ...c.methodological_trends.map((t) => `- ${t}`), ""] : []),
      ...(c.key_findings.length > 0 ? ["## Key Findings", ...c.key_findings.map((f) => `- ${f}`), ""] : []),
      ...(c.contradictions.length > 0 ? ["## Contradictions", ...c.contradictions.map((f) => `- ${f}`), ""] : []),
      ...(c.research_gaps.length > 0 ? ["## Research Gaps", ...c.research_gaps.map((g) => `- ${g}`), ""] : []),
      ...(c.future_directions.length > 0 ? ["## Future Directions", ...c.future_directions.map((d) => `- ${d}`), ""] : []),
      ...(c.references.length > 0
        ? ["## References", ...c.references.map((r, i) => `[${i + 1}] ${r.title}${r.authors ? ` — ${r.authors}` : ""}${r.year ? ` (${r.year})` : ""}`)]
        : []),
    ];
    const blob = new Blob([lines.join("\n")], { type: "text/markdown" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `literature-review.md`;
    a.click();
    URL.revokeObjectURL(url);
  }

  // ── Loading state ───────────────────────────────────────────────────────────
  if (status === "loading") {
    return (
      <Card className="flex flex-col items-center gap-3 px-6 py-16 text-center">
        <span className="flex h-12 w-12 animate-pulse items-center justify-center rounded-full bg-teal-50">
          <Sparkles className="h-5 w-5 text-teal-600" />
        </span>
        <p className="text-sm text-ink-soft">Loading…</p>
      </Card>
    );
  }

  // ── No papers ───────────────────────────────────────────────────────────────
  if (paperCount === 0) {
    return (
      <EmptyState
        icon={Sparkles}
        title="Add papers to generate a review"
        description="Save at least one paper to this project before drafting a literature review."
      />
    );
  }

  // ── Idle — no review yet ────────────────────────────────────────────────────
  if (status === "idle") {
    return (
      <Card className="flex flex-col items-center gap-4 px-6 py-16 text-center">
        <span className="flex h-12 w-12 items-center justify-center rounded-full bg-teal-50">
          <Sparkles className="h-5.5 w-5.5 text-teal-600" />
        </span>
        <div>
          <h3 className="font-display text-lg font-medium text-ink">Draft a literature review</h3>
          <p className="mx-auto mt-1.5 max-w-sm text-sm text-ink-soft">
            SAIRA will synthesize the {paperCount} saved paper{paperCount === 1 ? "" : "s"} in this project
            into a structured first draft, with citations you can verify.
          </p>
          <p className="mt-2 text-xs text-ink-faint">
            This runs a multi-stage AI pipeline and may take 30–90 seconds.
          </p>
        </div>
        <Button onClick={() => generate(false)} className="mt-1 gap-1.5">
          <Sparkles className="h-3.5 w-3.5" />
          Generate review
        </Button>
      </Card>
    );
  }

  // ── Generating ──────────────────────────────────────────────────────────────
  if (status === "generating") {
    return (
      <Card className="flex flex-col items-center gap-4 px-6 py-16 text-center">
        <span className="flex h-12 w-12 animate-pulse items-center justify-center rounded-full bg-teal-50">
          <Sparkles className="h-5 w-5 text-teal-600" />
        </span>
        <div>
          <p className="font-medium text-ink">Generating your literature review…</p>
          <p className="mt-1 text-sm text-ink-soft">
            SAIRA is reading {paperCount} paper{paperCount !== 1 ? "s" : ""} and drafting a synthesis.
            This may take 30–90 seconds.
          </p>
        </div>
        <div className="flex gap-1 mt-2">
          {[0, 1, 2].map((i) => (
            <span
              key={i}
              className="h-2 w-2 rounded-full bg-teal-500 animate-bounce"
              style={{ animationDelay: `${i * 150}ms` }}
            />
          ))}
        </div>
      </Card>
    );
  }

  // ── Error ───────────────────────────────────────────────────────────────────
  if (status === "error") {
    return (
      <Card className="flex flex-col items-center gap-4 px-6 py-12 text-center">
        <span className="flex h-12 w-12 items-center justify-center rounded-full bg-red-50">
          <AlertTriangle className="h-5 w-5 text-red-500" />
        </span>
        <div>
          <p className="font-medium text-ink">Generation failed</p>
          <p className="mt-1 text-sm text-ink-soft">{error}</p>
        </div>
        <Button variant="outline" onClick={() => generate(false)} className="gap-1.5">
          <RefreshCw className="h-3.5 w-3.5" />
          Try again
        </Button>
      </Card>
    );
  }

  // ── Done — show review ──────────────────────────────────────────────────────
  if (!review) return null;
  const c = review.content;

  return (
    <div>
      {/* Toolbar */}
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="text-sm text-ink-soft">
            Generated from {review.paper_count} paper{review.paper_count !== 1 ? "s" : ""}
            {review.created_at && (
              <span className="ml-2 text-xs text-ink-faint">
                · {new Date(review.created_at).toLocaleDateString()}
              </span>
            )}
          </p>
          {review.is_stale && (
            <div className="mt-1.5 flex items-center gap-1.5 text-xs text-amber-600">
              <AlertTriangle className="h-3.5 w-3.5" />
              Papers have been added since this review was generated. Regenerate to include them.
            </div>
          )}
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" className="gap-1.5" onClick={copy}>
            {copied ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
            {copied ? "Copied" : "Copy"}
          </Button>
          <Button variant="outline" size="sm" className="gap-1.5" onClick={exportMd}>
            <Download className="h-3.5 w-3.5" />
            Export .md
          </Button>
          <Button variant="secondary" size="sm" className="gap-1.5" onClick={() => generate(true)}>
            <RefreshCw className="h-3.5 w-3.5" />
            Regenerate
          </Button>
        </div>
      </div>

      {/* Review content */}
      <Card className="divide-y divide-line-soft p-7 space-y-5">
        <div className="pb-5">
          <h2 className="font-display text-xl font-semibold text-ink mb-3">{c.title}</h2>
          <p className="text-sm text-ink-soft leading-relaxed whitespace-pre-line">{c.overview}</p>
        </div>

        {c.themes && c.themes.length > 0 && (
          <Section title="Themes">
            <div className="grid gap-3 sm:grid-cols-2">
              {c.themes.map((t, i) => <ThemeCard key={i} theme={t} idx={i} />)}
            </div>
          </Section>
        )}

        {c.methodological_trends && c.methodological_trends.length > 0 && (
          <Section title="Methodological Trends">
            <BulletList items={c.methodological_trends} />
          </Section>
        )}

        {c.key_findings && c.key_findings.length > 0 && (
          <Section title="Key Findings">
            <BulletList items={c.key_findings} />
          </Section>
        )}

        {c.contradictions && c.contradictions.length > 0 && (
          <Section title="Contradictions & Debates">
            <BulletList items={c.contradictions} />
          </Section>
        )}

        {c.research_gaps && c.research_gaps.length > 0 && (
          <Section title="Research Gaps">
            <BulletList items={c.research_gaps} />
          </Section>
        )}

        {c.future_directions && c.future_directions.length > 0 && (
          <Section title="Future Directions">
            <BulletList items={c.future_directions} />
          </Section>
        )}

        {(c.datasets?.length > 0 || c.models?.length > 0) && (
          <Section title="Datasets & Models Used">
            {c.datasets?.length > 0 && (
              <div className="mb-3">
                <p className="mb-1 text-xs font-semibold text-ink-faint uppercase tracking-wider">Datasets</p>
                <BulletList items={c.datasets} />
              </div>
            )}
            {c.models?.length > 0 && (
              <div>
                <p className="mb-1 text-xs font-semibold text-ink-faint uppercase tracking-wider">Models & Architectures</p>
                <BulletList items={c.models} />
              </div>
            )}
          </Section>
        )}

        {c.references && c.references.length > 0 && (
          <Section title={`References (${c.references.length})`}>
            <div className="space-y-2">
              {c.references.map((r, i) => <ReferenceItem key={r.paper_id} ref={r} idx={i} />)}
            </div>
          </Section>
        )}
      </Card>
    </div>
  );
}


