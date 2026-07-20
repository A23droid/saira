"use client";

import { useState } from "react";
import { Sparkles, Copy, Download, RefreshCw, Check } from "lucide-react";
import { Paper } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { MarkdownViewer } from "@/components/shared/markdown-viewer";
import { EmptyState } from "@/components/shared/empty-state";

function buildReview(papers: Paper[], topic: string) {
  const intro = `## Introduction\n\nThis review synthesizes ${papers.length} papers on ${topic}. Each subsection below traces one line of work and closes with open questions that remain across the set.`;

  const body = papers
    .map((p, i) => {
      return `### ${i + 1}. ${p.title} (${p.authors[0]?.name}${p.authors.length > 1 ? " et al." : ""}, ${p.year})\n\n${p.aiSummary.tldr} The authors report that ${p.aiSummary.keyFindings[0].toLowerCase()}\n\n**Method.** ${p.extracted.method}${p.extracted.dataset.length ? `, evaluated on ${p.extracted.dataset.join(", ")}` : ""}.\n\n**Limitations.** ${p.aiSummary.limitations[0]}`;
    })
    .join("\n\n");

  const synthesis = `## Synthesis\n\nAcross these papers, a common thread is a move toward architectures and training recipes that trade a small amount of task-specific accuracy for large gains in efficiency or generality. Where the papers diverge is in evaluation rigor: some rely on a narrow set of benchmarks, which leaves open how well the reported gains transfer to less-studied domains.\n\n## Open questions\n\n- How do these methods perform under distribution shift, beyond the benchmarks reported here?\n- Which findings depend on model scale, and which are scale-invariant?\n- Where would a controlled, head-to-head comparison change the current consensus?`;

  return `${intro}\n\n${body}\n\n${synthesis}`;
}

export function LiteratureReviewPanel({
  papers,
  topic,
}: {
  papers: Paper[];
  topic: string;
}) {
  const [status, setStatus] = useState<"idle" | "generating" | "done">("idle");
  const [review, setReview] = useState("");
  const [copied, setCopied] = useState(false);

  function generate() {
    setStatus("generating");
    setTimeout(() => {
      setReview(buildReview(papers, topic));
      setStatus("done");
    }, 1400);
  }

  function copy() {
    navigator.clipboard.writeText(review);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }

  if (papers.length === 0) {
    return (
      <EmptyState
        icon={Sparkles}
        title="Add papers to generate a review"
        description="Save at least one paper to this project before drafting a literature review."
      />
    );
  }

  if (status === "idle") {
    return (
      <Card className="flex flex-col items-center gap-4 px-6 py-16 text-center">
        <span className="flex h-12 w-12 items-center justify-center rounded-full bg-teal-50">
          <Sparkles className="h-5.5 w-5.5 text-teal-600" />
        </span>
        <div>
          <h3 className="font-display text-lg font-medium text-ink">Draft a literature review</h3>
          <p className="mx-auto mt-1.5 max-w-sm text-sm text-ink-soft">
            SAIRA will synthesize the {papers.length} saved paper{papers.length === 1 ? "" : "s"} in
            this project into a structured first draft, with citations you can verify.
          </p>
        </div>
        <Button onClick={generate} className="mt-1 gap-1.5">
          <Sparkles className="h-3.5 w-3.5" />
          Generate review
        </Button>
      </Card>
    );
  }

  if (status === "generating") {
    return (
      <Card className="flex flex-col items-center gap-3 px-6 py-16 text-center">
        <span className="flex h-12 w-12 animate-pulse items-center justify-center rounded-full bg-teal-50">
          <Sparkles className="h-5.5 w-5.5 text-teal-600" />
        </span>
        <p className="text-sm text-ink-soft">Reading {papers.length} papers and drafting a synthesis…</p>
      </Card>
    );
  }

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-ink-soft">
          Draft generated from {papers.length} paper{papers.length === 1 ? "" : "s"} in this project.
        </p>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" className="gap-1.5" onClick={copy}>
            {copied ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
            {copied ? "Copied" : "Copy"}
          </Button>
          <Button variant="outline" size="sm" className="gap-1.5">
            <Download className="h-3.5 w-3.5" />
            Export .md
          </Button>
          <Button variant="secondary" size="sm" className="gap-1.5" onClick={generate}>
            <RefreshCw className="h-3.5 w-3.5" />
            Regenerate
          </Button>
        </div>
      </div>
      <Card className="p-7">
        <MarkdownViewer content={review} />
      </Card>
    </div>
  );
}
