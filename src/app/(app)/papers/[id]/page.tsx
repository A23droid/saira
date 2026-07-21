"use client";

import { use, useState } from "react";
import Link from "next/link";
import { notFound } from "next/navigation";
import {
  FileText,
  Quote,
  ExternalLink,
  Sparkles,
  ListChecks,
  NotebookPen,
  BookmarkPlus,
  Plus,
  Share2,
  Waypoints,
} from "lucide-react";
import { PageHeader } from "@/components/shared/page-header";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { AIChatPanel } from "@/components/shared/ai-chat-panel";
import { ReadingProgressCard } from "@/components/shared/reading-progress";
import { GraphPlaceholder } from "@/components/shared/graph-placeholder";
import { RelatedPapersPanel } from "@/components/shared/related-papers-panel";
import { SavedArtifactsPanel } from "@/components/shared/saved-artifacts-panel";
import {
  getPaperById,
  getNotesForPaper,
  similarPapers,
  getRelatedLinksForPaper,
  getSavedArtifactsForPaper,
} from "@/lib/mock-data";

export default function PaperDetailsPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const paper = getPaperById(id);
  const [notes, setNotes] = useState(paper ? getNotesForPaper(paper.id) : []);
  const [draft, setDraft] = useState("");

  if (!paper) return notFound();

  const related = similarPapers(paper.id, 3);
  const relatedLinks = getRelatedLinksForPaper(paper.id);
  const artifacts = getSavedArtifactsForPaper(paper.id);

  function addNote() {
    if (!draft.trim()) return;
    setNotes((prev) => [
      { id: crypto.randomUUID(), paperId: paper!.id, content: draft.trim(), createdAt: "just now" },
      ...prev,
    ]);
    setDraft("");
  }

  return (
    <div>
      <PageHeader
        title={paper.title}
        subtitle={`${paper.authors.map((a) => a.name).join(", ")} · ${paper.venue} ${paper.year}`}
        actions={
          <Button variant="secondary" className="gap-1.5">
            <BookmarkPlus className="h-3.5 w-3.5" />
            Save to project
          </Button>
        }
      />

      <div className="mb-6 flex flex-wrap items-center gap-2">
        {paper.tags.map((t) => (
          <Badge key={t} variant="secondary">
            {t}
          </Badge>
        ))}
        <Badge variant="outline" className="gap-1">
          <Quote className="h-3 w-3" /> {paper.citationCount.toLocaleString()} citations
        </Badge>
        <Badge variant="outline" className="font-mono">
          {paper.source}
        </Badge>
      </div>

      <div className="grid gap-6 lg:grid-cols-5">
        <div className="lg:col-span-3">
          {/* PDF viewer placeholder */}
          <Card className="mb-6 flex aspect-[3/4] max-h-[420px] flex-col items-center justify-center gap-3 bg-paper-dim/40 p-8 text-center">
            <span className="flex h-12 w-12 items-center justify-center rounded-full bg-surface">
              <FileText className="h-5 w-5 text-ink-faint" />
            </span>
            <p className="text-sm font-medium text-ink">PDF preview isn't available in this MVP</p>
            <p className="max-w-xs text-xs text-ink-faint">
              In the full product, the original PDF renders here with searchable text and highlights.
            </p>
            <Button variant="outline" size="sm" className="gap-1.5">
              <ExternalLink className="h-3.5 w-3.5" />
              Open source page
            </Button>
          </Card>

          <div className="mb-6">
            <ReadingProgressCard status={paper.readingStatus} />
          </div>

          <Tabs defaultValue="summary">
            <TabsList className="flex-wrap">
              <TabsTrigger value="summary">AI summary</TabsTrigger>
              <TabsTrigger value="extracted">Extracted info</TabsTrigger>
              <TabsTrigger value="notes">Notes ({notes.length})</TabsTrigger>
              <TabsTrigger value="related">Related work</TabsTrigger>
              <TabsTrigger value="graphs">Graphs</TabsTrigger>
              <TabsTrigger value="artifacts">Artifacts</TabsTrigger>
            </TabsList>

            <TabsContent value="summary">
              <Card className="p-6">
                <div className="mb-4 flex items-center gap-2">
                  <Sparkles className="h-4 w-4 text-teal-600" />
                  <h3 className="font-medium text-ink">TL;DR</h3>
                </div>
                <p className="mb-6 text-[0.95rem] leading-relaxed text-ink-soft">{paper.aiSummary.tldr}</p>

                <h4 className="mb-2 text-sm font-medium text-ink">Key findings</h4>
                <ul className="mb-6 list-disc space-y-1.5 pl-5 text-sm leading-relaxed text-ink-soft">
                  {paper.aiSummary.keyFindings.map((f) => (
                    <li key={f}>{f}</li>
                  ))}
                </ul>

                <h4 className="mb-2 text-sm font-medium text-ink">Methodology</h4>
                <p className="mb-6 text-sm leading-relaxed text-ink-soft">{paper.aiSummary.methodology}</p>

                <h4 className="mb-2 text-sm font-medium text-ink">Limitations</h4>
                <ul className="list-disc space-y-1.5 pl-5 text-sm leading-relaxed text-ink-soft">
                  {paper.aiSummary.limitations.map((l) => (
                    <li key={l}>{l}</li>
                  ))}
                </ul>
              </Card>
            </TabsContent>

            <TabsContent value="extracted">
              <Card className="divide-y divide-line-soft p-0">
                <Row label="Problem" value={paper.extracted.problem} />
                <Row
                  label="Datasets"
                  value={
                    paper.extracted.dataset.length ? (
                      <div className="flex flex-wrap gap-1.5">
                        {paper.extracted.dataset.map((d) => (
                          <Badge key={d} variant="secondary">
                            {d}
                          </Badge>
                        ))}
                      </div>
                    ) : (
                      "—"
                    )
                  }
                />
                <Row label="Method" value={paper.extracted.method} />
                <Row
                  label="Metrics"
                  value={
                    paper.extracted.metrics.length ? (
                      <ul className="space-y-1 font-mono text-xs">
                        {paper.extracted.metrics.map((m) => (
                          <li key={m.name}>
                            {m.name}: <span className="text-teal-700">{m.value}</span>
                          </li>
                        ))}
                      </ul>
                    ) : (
                      "—"
                    )
                  }
                />
                <Row label="Code available" value={paper.extracted.codeAvailable ? "Yes" : "No"} />
              </Card>
            </TabsContent>

            <TabsContent value="notes">
              <div className="mb-4 flex items-start gap-2">
                <Textarea
                  value={draft}
                  onChange={(e) => setDraft(e.target.value)}
                  placeholder="Write a note about this paper…"
                  rows={2}
                  className="flex-1"
                />
                <Button onClick={addNote} disabled={!draft.trim()} size="icon" className="mt-0.5">
                  <Plus className="h-4 w-4" />
                </Button>
              </div>
              {notes.length === 0 ? (
                <p className="rounded-xl border border-dashed border-line px-4 py-8 text-center text-sm text-ink-faint">
                  No notes yet — jot down a thought above.
                </p>
              ) : (
                <div className="flex flex-col gap-3">
                  {notes.map((n) => (
                    <Card key={n.id} className="p-4">
                      {n.highlight && (
                        <p className="mb-2 rounded-lg bg-teal-50 px-3 py-2 text-xs italic text-teal-700">
                          “{n.highlight}”
                        </p>
                      )}
                      <p className="text-sm text-ink">{n.content}</p>
                      <p className="mt-2 flex items-center gap-1 text-xs text-ink-faint">
                        <NotebookPen className="h-3 w-3" /> {n.createdAt}
                      </p>
                    </Card>
                  ))}
                </div>
              )}
            </TabsContent>

            <TabsContent value="related">
              <p className="mb-4 text-sm text-ink-soft">
                Papers SAIRA has identified as agreeing with or challenging this one's claims.
              </p>
              <RelatedPapersPanel links={relatedLinks} />
            </TabsContent>

            <TabsContent value="graphs">
              <div className="grid gap-5 sm:grid-cols-2">
                <GraphPlaceholder
                  icon={Share2}
                  title="Citation graph"
                  description="Papers this one cites, and papers that cite it, visualized as a network."
                />
                <GraphPlaceholder
                  icon={Waypoints}
                  title="Concept graph"
                  description="Key concepts in this paper and how they connect to related work."
                  accent="brass"
                />
              </div>
            </TabsContent>

            <TabsContent value="artifacts">
              <p className="mb-4 text-sm text-ink-soft">
                Ask AI answers and review snippets you've pinned from this paper.
              </p>
              <SavedArtifactsPanel artifacts={artifacts} />
            </TabsContent>
          </Tabs>
        </div>

        <div className="flex flex-col gap-6 lg:col-span-2">
          <div className="h-[420px]">
            <AIChatPanel
              initialMessages={[]}
              contextLabel={`Answering from “${paper.title.slice(0, 30)}${paper.title.length > 30 ? "…" : ""}”`}
              placeholder="Ask a question about this paper…"
            />
          </div>

          <div>
            <div className="mb-3 flex items-center gap-2">
              <ListChecks className="h-4 w-4 text-teal-600" />
              <h3 className="font-medium text-ink">Similar papers</h3>
            </div>
            <div className="flex flex-col gap-2">
              {related.map((p) => (
                <Link
                  key={p.id}
                  href={`/papers/${p.id}`}
                  className="rounded-xl border border-line bg-surface p-3.5 hover:border-teal-500/60"
                >
                  <p className="text-sm font-medium leading-snug text-ink">{p.title}</p>
                  <p className="mt-1 text-xs text-ink-faint">
                    {p.authors[0]?.name} et al. · {p.year}
                  </p>
                </Link>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="grid grid-cols-3 gap-4 p-5">
      <p className="text-xs font-medium uppercase tracking-wide text-ink-faint">{label}</p>
      <div className="col-span-2 text-sm text-ink">{value}</div>
    </div>
  );
}
