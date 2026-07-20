"use client";

import { use, useMemo, useState } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import Link from "next/link";
import {
  FileStack,
  NotebookPen,
  Users,
  Plus,
  Calendar,
} from "lucide-react";
import { PageHeader } from "@/components/shared/page-header";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { MilestoneTrail } from "@/components/shared/trail-divider";
import { PaperCard } from "@/components/shared/paper-card";
import { EmptyState } from "@/components/shared/empty-state";
import { AIChatPanel } from "@/components/shared/ai-chat-panel";
import { ComparePanel } from "@/components/shared/compare-panel";
import { LiteratureReviewPanel } from "@/components/shared/literature-review-panel";
import { getProjectById, getPapersForProject, chatMessages, notes as allNotes } from "@/lib/mock-data";
import { notFound } from "next/navigation";

export default function ProjectDetailsPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const project = getProjectById(id);
  const searchParams = useSearchParams();
  const router = useRouter();
  const initialTab = searchParams.get("tab") || "overview";
  const [compareSelection, setCompareSelection] = useState<string[]>([]);

  if (!project) return notFound();

  const projectPapers = getPapersForProject(project.id);
  const projectNotes = allNotes.filter((n) => projectPapers.some((p) => p.id === n.paperId));
  const selectedPapers = projectPapers.filter((p) => compareSelection.includes(p.id));

  const milestones = [
    { label: "Papers added", done: project.milestones.papersAdded },
    { label: "Notes taken", done: project.milestones.notesTaken },
    { label: "Compared", done: project.milestones.compared },
    { label: "Review drafted", done: project.milestones.reviewGenerated },
  ];

  return (
    <div>
      <PageHeader
        title={project.name}
        subtitle={project.description}
        actions={
          <Link href="/search">
            <Button className="gap-1.5">
              <Plus className="h-3.5 w-3.5" />
              Add papers
            </Button>
          </Link>
        }
      />

      <Tabs
        defaultValue={initialTab}
        onValueChange={(v) => router.replace(`/projects/${project.id}?tab=${v}`, { scroll: false })}
      >
        <TabsList className="flex-wrap">
          <TabsTrigger value="overview">Overview</TabsTrigger>
          <TabsTrigger value="papers">Papers ({projectPapers.length})</TabsTrigger>
          <TabsTrigger value="chat">Chat</TabsTrigger>
          <TabsTrigger value="compare">Compare</TabsTrigger>
          <TabsTrigger value="review">Literature review</TabsTrigger>
        </TabsList>

        <TabsContent value="overview">
          <div className="grid gap-5 lg:grid-cols-3">
            <Card className="p-6 lg:col-span-2">
              <h3 className="font-display text-lg font-medium text-ink">Project trail</h3>
              <p className="mt-1 text-sm text-ink-soft">
                The four waypoints most literature reviews pass through.
              </p>
              <div className="mt-6">
                <MilestoneTrail milestones={milestones} />
              </div>
            </Card>

            <Card className="flex flex-col gap-4 p-6">
              <div className="flex items-center gap-2 text-sm font-medium text-ink">
                <Calendar className="h-4 w-4 text-ink-faint" /> Created
              </div>
              <p className="-mt-2 text-sm text-ink-soft">{project.createdAt}</p>
              <div className="flex items-center gap-2 text-sm font-medium text-ink">
                <Users className="h-4 w-4 text-ink-faint" /> Collaborators
              </div>
              <div className="-mt-2 flex items-center gap-2">
                {project.collaborators.map((c) => (
                  <div key={c.name} className="flex items-center gap-1.5">
                    <Avatar className="h-6 w-6">
                      <AvatarFallback className="text-[10px]">{c.avatarInitial}</AvatarFallback>
                    </Avatar>
                    <span className="text-xs text-ink-soft">{c.name}</span>
                  </div>
                ))}
              </div>
            </Card>
          </div>

          <div className="mt-5 grid gap-5 sm:grid-cols-2">
            <Card className="p-6">
              <div className="mb-3 flex items-center gap-2">
                <FileStack className="h-4 w-4 text-teal-600" />
                <h3 className="font-medium text-ink">Papers</h3>
              </div>
              <p className="font-display text-3xl text-ink">{projectPapers.length}</p>
              <p className="mt-1 text-sm text-ink-soft">saved to this project</p>
            </Card>
            <Card className="p-6">
              <div className="mb-3 flex items-center gap-2">
                <NotebookPen className="h-4 w-4 text-teal-600" />
                <h3 className="font-medium text-ink">Notes</h3>
              </div>
              <p className="font-display text-3xl text-ink">{projectNotes.length}</p>
              <p className="mt-1 text-sm text-ink-soft">notes across saved papers</p>
            </Card>
          </div>
        </TabsContent>

        <TabsContent value="papers">
          {projectPapers.length === 0 ? (
            <EmptyState
              icon={FileStack}
              title="No papers yet"
              description="Search the library and save papers here to start building this project's trail."
              actionLabel="Search papers"
              onAction={() => router.push("/search")}
            />
          ) : (
            <div className="flex flex-col gap-3">
              {projectPapers.map((p) => (
                <PaperCard key={p.id} paper={p} />
              ))}
            </div>
          )}
        </TabsContent>

        <TabsContent value="chat">
          <div className="h-[560px]">
            <AIChatPanel
              initialMessages={chatMessages}
              contextLabel={`Answering from ${projectPapers.length} papers in ${project.name}`}
            />
          </div>
        </TabsContent>

        <TabsContent value="compare">
          {projectPapers.length < 2 ? (
            <EmptyState
              icon={FileStack}
              title="Add at least two papers to compare"
              description="Comparison works once this project has two or more saved papers."
              actionLabel="Search papers"
              onAction={() => router.push("/search")}
            />
          ) : (
            <>
              <p className="mb-3 text-sm text-ink-soft">Choose up to 4 papers to line up side by side.</p>
              <div className="mb-5 flex flex-col gap-2">
                {projectPapers.map((p) => (
                  <label
                    key={p.id}
                    className="flex items-center gap-3 rounded-xl border border-line bg-surface px-4 py-3 text-sm hover:border-teal-500/60"
                  >
                    <Checkbox
                      checked={compareSelection.includes(p.id)}
                      onCheckedChange={(checked) => {
                        setCompareSelection((prev) =>
                          checked
                            ? prev.length < 4
                              ? [...prev, p.id]
                              : prev
                            : prev.filter((id) => id !== p.id)
                        );
                      }}
                    />
                    <span className="text-ink">{p.title}</span>
                  </label>
                ))}
              </div>
              {selectedPapers.length >= 2 ? (
                <ComparePanel
                  papers={selectedPapers}
                  onRemove={(id) => setCompareSelection((prev) => prev.filter((p) => p !== id))}
                />
              ) : (
                <p className="text-sm text-ink-faint">Select at least two papers above to compare.</p>
              )}
            </>
          )}
        </TabsContent>

        <TabsContent value="review">
          <LiteratureReviewPanel papers={projectPapers} topic={project.name.toLowerCase()} />
        </TabsContent>
      </Tabs>
    </div>
  );
}
