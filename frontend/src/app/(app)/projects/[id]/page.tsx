"use client";

import { use, useState, useEffect } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import Link from "next/link";
import {
  FileStack,
  NotebookPen,
  Users,
  Plus,
  Calendar,
  Share2,
  Waypoints,
  Settings,
  Trash2,
  Edit2
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
import { SavedArtifactsPanel } from "@/components/shared/saved-artifacts-panel";
import { CitationGraph } from "@/components/shared/citation-graph";
import { ConceptGraph } from "@/components/shared/concept-graph";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";

import { Project } from "@/lib/types";
import { BackendPaper } from "@/lib/api/papers";
import { getProjectById, getProjectPapers, getProjectStats, updateProject, deleteProject, removePaperFromProject, getSavedArtifacts } from "@/lib/api/projects";
import { logHistoryEvent } from "@/lib/api/analytics";
import { generateComparison, Comparison } from "@/lib/api/comparisons";
import { CitationGraphData, ConceptGraphData, getProjectCitationGraph, getProjectConceptGraph } from "@/lib/api/projects";

const colorOptions = [
  { id: "teal", label: "Teal", className: "bg-teal-600" },
  { id: "brass", label: "Brass", className: "bg-brass-600" },
  { id: "ink", label: "Ink", className: "bg-ink" },
] as const;

export default function ProjectDetailsPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const searchParams = useSearchParams();
  const router = useRouter();
  const initialTab = searchParams.get("tab") || "overview";
  
  const [project, setProject] = useState<Project | null>(null);
  const [projectPapers, setProjectPapers] = useState<BackendPaper[]>([]);
  const [projectArtifacts, setProjectArtifacts] = useState<any[]>([]);
  const [stats, setStats] = useState<{total_papers: number, total_notes: number}>({ total_papers: 0, total_notes: 0 });
  const [loading, setLoading] = useState(true);
  const [notFound, setNotFound] = useState(false);
  
  const [compareSelection, setCompareSelection] = useState<string[]>([]);
  const [isComparing, setIsComparing] = useState(false);
  const [aiComparison, setAiComparison] = useState<Comparison | null>(null);
  
  const [citationGraph, setCitationGraph] = useState<CitationGraphData | null>(null);
  const [conceptGraph, setConceptGraph] = useState<ConceptGraphData | null>(null);

  const [isEditDialogOpen, setIsEditDialogOpen] = useState(false);
  const [editName, setEditName] = useState("");
  const [editDescription, setEditDescription] = useState("");
  const [editColor, setEditColor] = useState<"teal"|"brass"|"ink">("teal");
  
  useEffect(() => {
    let active = true;
    setLoading(true);
    
    Promise.all([
      getProjectById(id),
      getProjectPapers(id),
      getProjectStats(id),
      getSavedArtifacts(id).catch(() => []),
      getProjectCitationGraph(id).catch(() => null),
      getProjectConceptGraph(id).catch(() => null)
    ])
    .then(([proj, papers, statsData, artifacts, cGraph, conGraph]) => {
      if (active) {
        setProject(proj);
        setStats(statsData);
        // Ensure UI mock mappings are handled for papers
        setProjectPapers(papers as any);
        setProjectArtifacts(artifacts);
        setCitationGraph(cGraph);
        setConceptGraph(conGraph);
        setEditName(proj.name);
        setEditDescription(proj.description || "");
        setEditColor((proj.color as any) || "teal");
        setLoading(false);
      }
    })
    .catch((err) => {
      console.error(err);
      if (err.status === 404) setNotFound(true);
      setLoading(false);
    });
    
    return () => { active = false; };
  }, [id]);

  useEffect(() => {
    if (project) {
      logHistoryEvent({
        event_type: "view_project",
        reference_id: project.id,
        title: project.name,
        url: `/projects/${project.id}`,
      }).catch(console.error);
    }
  }, [project]);

  if (loading) return <div className="p-10 text-center text-ink-faint">Loading project...</div>;
  if (notFound || !project) return <div className="p-10 text-center text-red-500">Project not found.</div>;

  const projectNotesCount = stats.total_notes; 
  const selectedPapers = projectPapers.filter((p) => compareSelection.includes(p.id));

  const milestones = [
    { label: "Papers added", done: projectPapers.length > 0 },
    { label: "Notes taken", done: projectNotesCount > 0 },
    { label: "Compared", done: false },
    { label: "Review drafted", done: false },
  ];

  const handleEditSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const updated = await updateProject(project.id, {
        name: editName,
        description: editDescription,
        color: editColor
      });
      setProject({ ...project, ...updated });
      setIsEditDialogOpen(false);
    } catch (err) {
      console.error(err);
    }
  };

  const handleDeleteProject = async () => {
    if (confirm("Are you sure you want to delete this project? This cannot be undone.")) {
      try {
        await deleteProject(project.id);
        router.push("/projects");
      } catch (err) {
        console.error(err);
      }
    }
  };

  return (
    <div>
      <PageHeader
        title={project.name}
        subtitle={project.description || "No description provided."}
        actions={
          <div className="flex gap-2 items-center">
            <Link href="/search">
              <Button className="gap-1.5">
                <Plus className="h-3.5 w-3.5" />
                Add papers
              </Button>
            </Link>
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="ghost" size="icon">
                  <Settings className="h-4 w-4" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                <DropdownMenuItem onClick={() => setIsEditDialogOpen(true)}>
                  <Edit2 className="mr-2 h-4 w-4" />
                  Edit Project
                </DropdownMenuItem>
                <DropdownMenuItem className="text-red-600" onClick={handleDeleteProject}>
                  <Trash2 className="mr-2 h-4 w-4" />
                  Delete Project
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        }
      />

      <Tabs
        defaultValue={initialTab}
        onValueChange={(v) => router.replace(`/projects/${project.id}?tab=${v}`, { scroll: false })}
      >
        <TabsList className="flex-wrap">
          <TabsTrigger value="overview">Overview</TabsTrigger>
          <TabsTrigger value="workspace">Workspace</TabsTrigger>
          <TabsTrigger value="visualization">Visualization</TabsTrigger>
          <TabsTrigger value="synthesis">Synthesis</TabsTrigger>
          <TabsTrigger value="artifacts">Saved</TabsTrigger>
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
              <p className="-mt-2 text-sm text-ink-soft">{new Date(project.created_at || "").toLocaleDateString()}</p>
              
              <div className="flex items-center gap-2 text-sm font-medium text-ink mt-2">
                <Calendar className="h-4 w-4 text-ink-faint" /> Last updated
              </div>
              <p className="-mt-2 text-sm text-ink-soft">{new Date(project.updated_at || "").toLocaleDateString()}</p>
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
              <p className="font-display text-3xl text-ink">{projectNotesCount}</p>
              <p className="mt-1 text-sm text-ink-soft">notes across saved papers</p>
            </Card>
          </div>
        </TabsContent>

        <TabsContent value="workspace">
          <Tabs defaultValue="papers" className="w-full">
            <TabsList className="mb-4">
              <TabsTrigger value="papers">Papers ({projectPapers.length})</TabsTrigger>
              <TabsTrigger value="chat">Chat</TabsTrigger>
            </TabsList>
            
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
                    <div key={p.id} className="relative group">
                      <PaperCard paper={{
                        id: p.id,
                        title: p.title,
                        abstract: p.abstract || "",
                        year: p.publication_year || 0,
                        venue: p.venue || "",
                        citationCount: p.citation_count || 0,
                        source: (p.source || "web") as any,
                        authors: [],
                        tags: [],
                        savedToProjectIds: [],
                        readingStatus: "unread",
                        extracted: { problem: "", dataset: [], method: "", metrics: [], codeAvailable: false },
                        aiSummary: { tldr: "", keyFindings: [], methodology: "", limitations: [] }
                      }} />
                      <Button
                        variant="destructive"
                        size="icon"
                        className="absolute top-4 right-4 opacity-0 group-hover:opacity-100 transition-opacity"
                        onClick={async () => {
                          if (confirm("Remove this paper from the project?")) {
                            try {
                              await removePaperFromProject(project.id, p.id);
                              setProjectPapers((prev) => prev.filter((paper) => paper.id !== p.id));
                            } catch (err) {
                              console.error("Failed to remove paper:", err);
                            }
                          }
                        }}
                      >
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    </div>
                  ))}
                </div>
              )}
            </TabsContent>
            
            <TabsContent value="chat">
              <div className="h-[600px] mt-6">
                <AIChatPanel
                  projectId={project.id}
                  contextLabel={`Project: ${project.name}`}
                  placeholder="Ask about any paper in this project..."
                />
              </div>
            </TabsContent>
          </Tabs>
        </TabsContent>

        <TabsContent value="visualization">
          <div className="grid gap-5 sm:grid-cols-2">
            {citationGraph && citationGraph.nodes.length > 0 ? (
              <div className="sm:col-span-2">
                <CitationGraph data={citationGraph} />
              </div>
            ) : (
              <EmptyState
                icon={Share2}
                title="No citation graph"
                description="Add papers to this project to visualize their citation network."
              />
            )}
            
            {conceptGraph && conceptGraph.nodes.length > 0 ? (
              <div className="sm:col-span-2 mt-2 border-t border-line pt-5">
                <ConceptGraph data={conceptGraph} />
              </div>
            ) : (
              <EmptyState
                icon={Waypoints}
                title="No concept graph"
                description="Add papers to this project to visualize shared concepts and methods."
              />
            )}
          </div>
        </TabsContent>

        <TabsContent value="synthesis">
          <Tabs defaultValue="compare" className="w-full">
            <TabsList className="mb-4">
              <TabsTrigger value="compare">Compare</TabsTrigger>
              <TabsTrigger value="review">Literature Review</TabsTrigger>
            </TabsList>

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
                        className="flex items-center gap-3 rounded-xl border border-line bg-surface px-4 py-3 text-sm hover:border-teal-500/60 cursor-pointer"
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
                        <span className="text-ink font-medium">{p.title}</span>
                      </label>
                    ))}
                  </div>
                  {selectedPapers.length >= 2 ? (
                    <div className="flex flex-col gap-6 mt-6">
                      
                      <div className="border border-line rounded-2xl p-6 bg-surface">
                        <div className="flex items-center justify-between mb-4">
                          <h3 className="font-display text-lg font-medium text-ink">AI Synthesis</h3>
                          <Button 
                            onClick={async () => {
                              setIsComparing(true);
                              setAiComparison(null);
                              try {
                                const title = `Comparison of ${selectedPapers.length} papers`;
                                const res = await generateComparison(title, selectedPapers.map(p => p.id), project.id);
                                setAiComparison(res);
                              } catch(e) {
                                console.error(e);
                              } finally {
                                setIsComparing(false);
                              }
                            }}
                            disabled={isComparing}
                          >
                            {isComparing ? "Analyzing..." : "Generate AI Comparison"}
                          </Button>
                        </div>
                        
                        {aiComparison && (
                          <ComparePanel
                            papers={selectedPapers}
                            comparison={aiComparison}
                            onRemove={(pid) => setCompareSelection(prev => prev.filter(x => x !== pid))}
                            projectId={project.id}
                          />
                        )}
                      </div>
                    </div>
                  ) : (
                    <p className="text-sm text-ink-faint">Select at least two papers above to compare.</p>
                  )}
                </>
              )}
            </TabsContent>

            <TabsContent value="review">
              <LiteratureReviewPanel projectId={project.id} paperCount={projectPapers.length} />
            </TabsContent>
          </Tabs>
        </TabsContent>

        <TabsContent value="artifacts">
          <p className="mb-4 text-sm text-ink-soft">
            Answers and snippets you've pinned from Ask AI and the literature review draft.
          </p>
          <SavedArtifactsPanel artifacts={projectArtifacts} />
        </TabsContent>
      </Tabs>
      
      {/* Edit Project Dialog */}
      <Dialog open={isEditDialogOpen} onOpenChange={setIsEditDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Edit Project</DialogTitle>
            <DialogDescription>
              Update your project's details below.
            </DialogDescription>
          </DialogHeader>
          <form onSubmit={handleEditSubmit} className="flex flex-col gap-5 mt-2">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="edit-name">Project name</Label>
              <Input
                id="edit-name"
                value={editName}
                onChange={(e) => setEditName(e.target.value)}
                required
              />
            </div>

            <div className="flex flex-col gap-1.5">
              <Label htmlFor="edit-desc">Description</Label>
              <Textarea
                id="edit-desc"
                value={editDescription}
                onChange={(e) => setEditDescription(e.target.value)}
                rows={3}
              />
            </div>

            <div className="flex flex-col gap-2">
              <Label>Color tag</Label>
              <div className="flex gap-3">
                {colorOptions.map((c) => (
                  <button
                    type="button"
                    key={c.id}
                    onClick={() => setEditColor(c.id)}
                    className={cn(
                      "flex h-9 w-9 items-center justify-center rounded-full border-2 transition-all",
                      editColor === c.id ? "border-ink scale-105" : "border-transparent"
                    )}
                    aria-label={c.label}
                  >
                    <span className={cn("h-5 w-5 rounded-full", c.className)} />
                  </button>
                ))}
              </div>
            </div>
            <DialogFooter>
              <Button type="button" variant="ghost" onClick={() => setIsEditDialogOpen(false)}>Cancel</Button>
              <Button type="submit">Save changes</Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  );
}
