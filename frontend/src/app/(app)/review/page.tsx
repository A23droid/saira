"use client";

import { useEffect, useState } from "react";
import { PageHeader } from "@/components/shared/page-header";
import { Sparkles, RefreshCw, Check, Copy, Download, AlertTriangle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { getPapers, BackendPaper } from "@/lib/api/papers";
import { generateIndependentReview } from "@/lib/api/project_ai";
import { LiteratureReviewContent, LitReviewTheme, LitReviewReference } from "@/lib/api/project_ai";

// -- Section helpers
function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="border-b border-line-soft pb-5 last:border-0 mb-5">
      <h3 className="mb-3 font-display text-[0.95rem] font-semibold text-ink">{title}</h3>
      {children}
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
    <div className="rounded-xl border border-line bg-paper-dim/30 p-4 relative group">
      <p className="mb-1.5 text-xs font-semibold uppercase tracking-wider text-teal-600">
        Theme {idx + 1}
      </p>
      <h4 className="mb-2 pr-12 font-display text-sm font-semibold text-ink">{theme.title}</h4>
      <p className="text-sm text-ink-soft leading-relaxed">{theme.summary}</p>
      {theme.paper_ids && theme.paper_ids.length > 0 && (
        <p className="mt-2 text-xs text-ink-faint">
          Based on {theme.paper_ids.length} paper{theme.paper_ids.length !== 1 ? "s" : ""}
        </p>
      )}
    </div>
  );
}

export default function ReviewGeneratorPage() {
  const [papers, setPapers] = useState<BackendPaper[]>([]);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  
  const [status, setStatus] = useState<"idle" | "generating" | "done" | "error">("idle");
  const [review, setReview] = useState<LiteratureReviewContent | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    getPapers().then(data => {
      setPapers(data);
      setLoading(false);
    }).catch(e => {
      console.error(e);
      setLoading(false);
    });
  }, []);

  const togglePaper = (id: string) => {
    setSelectedIds(prev => prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id]);
  };

  const handleGenerate = async () => {
    if (selectedIds.length === 0) return;
    setStatus("generating");
    setError(null);
    try {
      const content = await generateIndependentReview(selectedIds);
      setReview(content);
      setStatus("done");
    } catch (e: any) {
      setError(e.message || "Failed to generate review");
      setStatus("error");
    }
  };

  function copy() {
    if (!review) return;
    const c = review;
    const text = [
      `# ${c.title}`,
      "",
      "## Overview",
      c.overview,
      "",
      ...(c.themes?.length > 0
        ? ["## Themes", ...c.themes.map((t) => `### ${t.title}\n${t.summary}`), ""]
        : []),
      ...(c.key_findings?.length > 0 ? ["## Key Findings", ...c.key_findings.map((f) => `- ${f}`), ""] : []),
      ...(c.research_gaps?.length > 0 ? ["## Research Gaps", ...c.research_gaps.map((g) => `- ${g}`), ""] : []),
      ...(c.future_directions?.length > 0 ? ["## Future Directions", ...c.future_directions.map((d) => `- ${d}`), ""] : []),
      ...(c.references?.length > 0
        ? ["## References", ...c.references.map((r, i) => `[${i + 1}] ${r.title}${r.authors ? ` — ${r.authors}` : ""}${r.year ? ` (${r.year})` : ""}`)]
        : []),
    ].join("\n");
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }

  function exportMd() {
    if (!review) return;
    const c = review;
    const lines = [
      `# ${c.title}`,
      "",
      "## Overview",
      c.overview,
      "",
      ...(c.themes?.length > 0
        ? ["## Themes", ...c.themes.flatMap((t) => [`### ${t.title}`, t.summary, ""]), ""]
        : []),
      ...(c.methodological_trends?.length > 0 ? ["## Methodological Trends", ...c.methodological_trends.map((t) => `- ${t}`), ""] : []),
      ...(c.key_findings?.length > 0 ? ["## Key Findings", ...c.key_findings.map((f) => `- ${f}`), ""] : []),
      ...(c.contradictions?.length > 0 ? ["## Contradictions", ...c.contradictions.map((f) => `- ${f}`), ""] : []),
      ...(c.research_gaps?.length > 0 ? ["## Research Gaps", ...c.research_gaps.map((g) => `- ${g}`), ""] : []),
      ...(c.future_directions?.length > 0 ? ["## Future Directions", ...c.future_directions.map((d) => `- ${d}`), ""] : []),
      ...(c.references?.length > 0
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

  return (
    <div className="pb-20">
      <PageHeader
        title="Literature review generator"
        subtitle="Choose a set of papers and let SAIRA draft a structured first pass."
      />
      <div className="mt-8 grid lg:grid-cols-12 gap-8 items-start">
        <div className="lg:col-span-4">
          <Card className="p-5 sticky top-6">
            <h3 className="font-display font-medium text-ink mb-4">Select Papers ({selectedIds.length})</h3>
            {loading ? (
              <p className="text-sm text-ink-soft">Loading papers...</p>
            ) : papers.length === 0 ? (
              <p className="text-sm text-ink-soft">You haven't saved any papers yet.</p>
            ) : (
              <div className="space-y-2 max-h-[500px] overflow-y-auto thin-scroll pr-2">
                {papers.map(p => {
                  const isSelected = selectedIds.includes(p.id);
                  return (
                    <div
                      key={p.id}
                      onClick={() => togglePaper(p.id)}
                      className={`p-3 rounded-lg border text-sm cursor-pointer transition-colors ${
                        isSelected 
                          ? "border-teal-500 bg-teal-50/50" 
                          : "border-line-soft hover:border-line bg-surface"
                      }`}
                    >
                      <p className="font-medium text-ink line-clamp-2">{p.title}</p>
                      {p.authors && <p className="text-xs text-ink-soft mt-1 line-clamp-1">{p.authors.map(a => a.name).join(", ")}</p>}
                    </div>
                  );
                })}
              </div>
            )}

            <Button 
              className="w-full mt-6 gap-1.5" 
              onClick={handleGenerate}
              disabled={selectedIds.length === 0 || status === "generating"}
            >
              <Sparkles className="h-4 w-4" />
              Generate Review
            </Button>
          </Card>
        </div>

        <div className="lg:col-span-8">
          {status === "idle" && (
            <Card className="flex flex-col items-center gap-4 px-6 py-16 text-center">
              <span className="flex h-12 w-12 items-center justify-center rounded-full bg-teal-50">
                <Sparkles className="h-5.5 w-5.5 text-teal-600" />
              </span>
              <div>
                <h3 className="font-display text-lg font-medium text-ink">Draft an independent review</h3>
                <p className="mx-auto mt-1.5 max-w-sm text-sm text-ink-soft">
                  Select papers from the sidebar and click generate. SAIRA will synthesize them into a structured first draft.
                </p>
              </div>
            </Card>
          )}

          {status === "generating" && (
            <Card className="flex flex-col items-center gap-4 px-6 py-16 text-center">
              <span className="flex h-12 w-12 animate-pulse items-center justify-center rounded-full bg-teal-50">
                <Sparkles className="h-5 w-5 text-teal-600" />
              </span>
              <div>
                <p className="font-medium text-ink">Generating your literature review…</p>
                <p className="mt-1 text-sm text-ink-soft">
                  SAIRA is reading {selectedIds.length} paper{selectedIds.length !== 1 ? "s" : ""} and drafting a synthesis.
                </p>
              </div>
            </Card>
          )}

          {status === "error" && (
            <Card className="flex flex-col items-center gap-4 px-6 py-12 text-center">
              <span className="flex h-12 w-12 items-center justify-center rounded-full bg-red-50">
                <AlertTriangle className="h-5 w-5 text-red-500" />
              </span>
              <div>
                <p className="font-medium text-ink">Generation failed</p>
                <p className="mt-1 text-sm text-ink-soft">{error}</p>
              </div>
            </Card>
          )}

          {status === "done" && review && (
            <div>
              <div className="mb-4 flex flex-wrap items-center justify-end gap-3">
                <div className="flex gap-2">
                  <Button variant="outline" size="sm" className="gap-1.5" onClick={copy}>
                    {copied ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
                    {copied ? "Copied" : "Copy"}
                  </Button>
                  <Button variant="outline" size="sm" className="gap-1.5" onClick={exportMd}>
                    <Download className="h-3.5 w-3.5" />
                    Export .md
                  </Button>
                </div>
              </div>

              <Card className="p-7">
                <div className="mb-8">
                  <h2 className="font-display text-xl font-semibold text-ink mb-3">{review.title}</h2>
                  <p className="text-sm text-ink-soft leading-relaxed whitespace-pre-line">{review.overview}</p>
                </div>

                {review.themes && review.themes.length > 0 && (
                  <Section title="Themes">
                    <div className="grid gap-3 sm:grid-cols-2">
                      {review.themes.map((t, i) => <ThemeCard key={i} theme={t} idx={i} />)}
                    </div>
                  </Section>
                )}

                {review.methodological_trends && review.methodological_trends.length > 0 && (
                  <Section title="Methodological Trends">
                    <BulletList items={review.methodological_trends} />
                  </Section>
                )}

                {review.key_findings && review.key_findings.length > 0 && (
                  <Section title="Key Findings">
                    <BulletList items={review.key_findings} />
                  </Section>
                )}

                {review.contradictions && review.contradictions.length > 0 && (
                  <Section title="Contradictions & Debates">
                    <BulletList items={review.contradictions} />
                  </Section>
                )}

                {review.research_gaps && review.research_gaps.length > 0 && (
                  <Section title="Research Gaps">
                    <BulletList items={review.research_gaps} />
                  </Section>
                )}

                {review.future_directions && review.future_directions.length > 0 && (
                  <Section title="Future Directions">
                    <BulletList items={review.future_directions} />
                  </Section>
                )}
              </Card>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
