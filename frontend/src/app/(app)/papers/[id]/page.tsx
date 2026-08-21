"use client";

import { use, useState, useEffect } from "react";
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
  AlertCircle,
  Star,
  Trash2,
  Highlighter
} from "lucide-react";
import { PageHeader } from "@/components/shared/page-header";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { AIChatPanel } from "@/components/shared/ai-chat-panel";
import { ReadingProgressCard } from "@/components/shared/reading-progress";
import { RelatedPapersPanel } from "@/components/shared/related-papers-panel";
import { SavedArtifactsPanel } from "@/components/shared/saved-artifacts-panel";
import { GraphPlaceholder } from "@/components/shared/graph-placeholder";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog";

import { apiFetch } from "@/lib/api/client";
import { getPaperById } from "@/lib/api/papers";
import { getProjects, addPaperToProject, updateProjectPaper } from "@/lib/api/projects";
import { getReadingData, createNote, deleteNote, createHighlight, deleteHighlight, updateReadingProgress, ProjectPaperReadingData } from "@/lib/api/reading_data";
import { Paper, Project } from "@/lib/types";

export default function PaperDetailsPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  
  const [paper, setPaper] = useState<Paper | null>(null);
  const [paperProjects, setPaperProjects] = useState<Project[]>([]);
  const [allProjects, setAllProjects] = useState<Project[]>([]);
  
  const [selectedProjectId, setSelectedProjectId] = useState<string>("");
  const [readingData, setReadingData] = useState<ProjectPaperReadingData | null>(null);
  
  const [draftNote, setDraftNote] = useState("");
  const [draftHighlightText, setDraftHighlightText] = useState("");
  const [draftHighlightNote, setDraftHighlightNote] = useState("");
  
  const [isDialogOpen, setIsDialogOpen] = useState(false);
  const [isHighlightDialogOpen, setIsHighlightDialogOpen] = useState(false);
  
  // Fetch Paper & Projects it belongs to
  useEffect(() => {
    let active = true;
    
    // Promise.all([
    //   apiFetch<Paper>(`/papers/${id}`),
    //   apiFetch<Project[]>(`/papers/${id}/projects`),
    //   getProjects()
    // ])
    Promise.all([
    getPaperById(id),
    apiFetch<Project[]>(`/papers/${id}/projects`),
    getProjects(),
  ])
    .then(([p, pProjs, allProjs]) => {
      if (active) {
        // Map backend schema to frontend Paper
        const uiPaper = {
          ...p,
          year: p.publication_year ?? null,
          citationCount: p.citation_count ?? 0,
          authors: [],
          tags: [],
          readingStatus: "unread",
          aiSummary: { tldr: "", keyFindings: [], methodology: "", limitations: [] },
          extracted: { problem: "", dataset: [], method: "", metrics: [], codeAvailable: false }
        };
        setPaper(uiPaper as Paper);
        setPaperProjects(pProjs);
        setAllProjects(allProjs);
        
        if (pProjs.length > 0) {
          setSelectedProjectId(pProjs[0].id);
        }
      }
    })
    .catch((err) => {
      console.error(err);
      if (err.status === 404) {
        // Handled below if paper remains null
      }
    });
    
    return () => { active = false; };
  }, [id]);

  // Fetch reading data when selected project changes
  useEffect(() => {
    if (!selectedProjectId) {
      setReadingData(null);
      return;
    }
    
    let active = true;
    getReadingData(selectedProjectId, id)
      .then((data) => {
        if (active) setReadingData(data);
      })
      .catch(console.error);
      
    return () => { active = false; };
  }, [selectedProjectId, id]);

  if (paper === null) return <div className="p-10 text-center">Loading...</div>;

  const handleAddNote = async () => {
    if (!draftNote.trim() || !selectedProjectId) return;
    try {
      const newNote = await createNote(selectedProjectId, paper.id, draftNote.trim());
      setReadingData(prev => prev ? {
        ...prev,
        notes: [newNote, ...prev.notes]
      } : null);
      setDraftNote("");
    } catch (err) {
      console.error("Failed to add note", err);
    }
  }

  const handleDeleteNote = async (noteId: string) => {
    if (!selectedProjectId) return;
    try {
      await deleteNote(selectedProjectId, paper.id, noteId);
      setReadingData(prev => prev ? {
        ...prev,
        notes: prev.notes.filter(n => n.id !== noteId)
      } : null);
    } catch (err) {
      console.error("Failed to delete note", err);
    }
  }
  
  const handleAddHighlight = async () => {
    if (!draftHighlightText.trim() || !selectedProjectId) return;
    try {
      const newHl = await createHighlight(selectedProjectId, paper.id, draftHighlightText.trim(), draftHighlightNote.trim());
      setReadingData(prev => prev ? {
        ...prev,
        highlights: [newHl, ...prev.highlights]
      } : null);
      setDraftHighlightText("");
      setDraftHighlightNote("");
      setIsHighlightDialogOpen(false);
    } catch (err) {
      console.error("Failed to add highlight", err);
    }
  }

  const handleDeleteHighlight = async (hlId: string) => {
    if (!selectedProjectId) return;
    try {
      await deleteHighlight(selectedProjectId, paper.id, hlId);
      setReadingData(prev => prev ? {
        ...prev,
        highlights: prev.highlights.filter(h => h.id !== hlId)
      } : null);
    } catch (err) {
      console.error("Failed to delete highlight", err);
    }
  }
  
  const handleSaveToProject = async (projId: string) => {
    try {
      await addPaperToProject(projId, paper.id, {});
      const newProj = allProjects.find(p => p.id === projId);
      if (newProj) {
        setPaperProjects(prev => [...prev, newProj]);
        setSelectedProjectId(projId);
      }
      setIsDialogOpen(false);
    } catch (err) {
      console.error("Failed to save", err);
    }
  }

  const toggleFavorite = async () => {
    if (!selectedProjectId || !readingData) return;
    try {
      const newFav = !readingData.favorite;
      await updateProjectPaper(selectedProjectId, paper.id, { favorite: newFav });
      setReadingData({ ...readingData, favorite: newFav });
    } catch (err) {
      console.error(err);
    }
  }

  const handleUpdateProgressPercent = async (percent: number) => {
    if (!selectedProjectId) return;
    try {
      const res = await updateReadingProgress(selectedProjectId, paper.id, percent);
      setReadingData(prev => prev ? { ...prev, reading_progress: res } : null);
    } catch (err) {
      console.error(err);
    }
  }

  const handleUpdateStatus = async (status: string) => {
    if (!selectedProjectId || !readingData) return;
    try {
      await updateProjectPaper(selectedProjectId, paper.id, { status });
      setReadingData({ ...readingData, status });
    } catch (err) {
      console.error(err);
    }
  }

  return (
    <div>
      <PageHeader
        title={paper.title}
        subtitle={`${paper.venue || "Unknown Venue"} ${paper.year || ""}`}
        actions={
          <div className="flex gap-2">
            {selectedProjectId && (
              <Button 
                variant={readingData?.favorite ? "default" : "outline"} 
                className="gap-1.5"
                onClick={toggleFavorite}
              >
                <Star className={`h-3.5 w-3.5 ${readingData?.favorite ? "fill-white" : ""}`} />
                {readingData?.favorite ? "Favorited" : "Favorite"}
              </Button>
            )}
            <Button variant="secondary" className="gap-1.5" onClick={() => setIsDialogOpen(true)}>
              <BookmarkPlus className="h-3.5 w-3.5" />
              Save to project
            </Button>
          </div>
        }
      />

      <div className="mb-6 flex flex-wrap items-center gap-2">
        <Badge variant="outline" className="gap-1">
          <Quote className="h-3 w-3" /> {paper.citationCount.toLocaleString()} citations
        </Badge>
        <Badge variant="outline" className="font-mono">
          {paper.source}
        </Badge>
        
        {paperProjects.length > 0 && (
          <div className="ml-auto flex items-center gap-2">
            <span className="text-sm text-ink-faint">Project Context:</span>
            <Select value={selectedProjectId} onValueChange={setSelectedProjectId}>
              <SelectTrigger className="w-48 h-8 text-xs">
                <SelectValue placeholder="Select project" />
              </SelectTrigger>
              <SelectContent>
                {paperProjects.map(p => (
                  <SelectItem key={p.id} value={p.id}>{p.name}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        )}
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

          {paper.abstract && (
            <Card className="mb-6 p-5">
              <h4 className="text-xs font-semibold uppercase tracking-wider text-ink-faint mb-2">Abstract</h4>
              <p className="text-sm leading-relaxed text-ink-soft">{paper.abstract}</p>
            </Card>
          )}

          <div className="mb-6">
            <ReadingProgressCard 
              percent={readingData?.reading_progress?.progress_percent || 0}
              status={readingData?.status || "unread"}
              onUpdatePercent={handleUpdateProgressPercent}
              onUpdateStatus={handleUpdateStatus}
              disabled={!selectedProjectId}
            />
          </div>

          <Tabs defaultValue="notes">
            <TabsList className="flex-wrap">
              <TabsTrigger value="notes">Notes ({readingData?.notes?.length || 0})</TabsTrigger>
              <TabsTrigger value="highlights">Highlights ({readingData?.highlights?.length || 0})</TabsTrigger>
              <TabsTrigger value="summary">AI summary</TabsTrigger>
              <TabsTrigger value="extracted">Extracted info</TabsTrigger>
              <TabsTrigger value="related">Related work</TabsTrigger>
              <TabsTrigger value="graphs">Graphs</TabsTrigger>
            </TabsList>

            <TabsContent value="notes">
              {!selectedProjectId ? (
                <Alert className="mb-4 bg-brass-50 border-brass-200">
                  <AlertCircle className="h-4 w-4 text-brass-700" />
                  <AlertTitle className="text-brass-800">No project context</AlertTitle>
                  <AlertDescription className="text-brass-700/80">
                    You must save this paper to a project before you can add notes, highlights, or track reading progress.
                  </AlertDescription>
                </Alert>
              ) : (
                <>
                  <div className="mb-4 flex items-start gap-2">
                    <Textarea
                      value={draftNote}
                      onChange={(e) => setDraftNote(e.target.value)}
                      placeholder="Write a note about this paper…"
                      rows={2}
                      className="flex-1"
                    />
                    <Button onClick={handleAddNote} disabled={!draftNote.trim()} size="icon" className="mt-0.5">
                      <Plus className="h-4 w-4" />
                    </Button>
                  </div>
                  {!readingData?.notes?.length ? (
                    <p className="rounded-xl border border-dashed border-line px-4 py-8 text-center text-sm text-ink-faint">
                      No notes yet — jot down a thought above.
                    </p>
                  ) : (
                    <div className="flex flex-col gap-3">
                      {readingData.notes.map((n) => (
                        <Card key={n.id} className="p-4 group relative">
                          <p className="text-sm text-ink">{n.content}</p>
                          <div className="mt-2 flex items-center justify-between text-xs text-ink-faint">
                            <span className="flex items-center gap-1">
                              <NotebookPen className="h-3 w-3" /> {new Date(n.created_at).toLocaleString()}
                            </span>
                            <button 
                              onClick={() => handleDeleteNote(n.id)}
                              className="opacity-0 group-hover:opacity-100 transition-opacity text-red-500 hover:text-red-700"
                            >
                              <Trash2 className="h-3.5 w-3.5" />
                            </button>
                          </div>
                        </Card>
                      ))}
                    </div>
                  )}
                </>
              )}
            </TabsContent>
            
            <TabsContent value="highlights">
              {!selectedProjectId ? (
                <Alert className="mb-4 bg-brass-50 border-brass-200">
                  <AlertCircle className="h-4 w-4 text-brass-700" />
                  <AlertTitle className="text-brass-800">No project context</AlertTitle>
                  <AlertDescription className="text-brass-700/80">
                    You must save this paper to a project before you can add highlights.
                  </AlertDescription>
                </Alert>
              ) : (
                <>
                  <div className="mb-4">
                    <Button variant="outline" size="sm" onClick={() => setIsHighlightDialogOpen(true)} className="gap-2">
                      <Highlighter className="h-4 w-4" /> Add manual highlight
                    </Button>
                  </div>
                  {!readingData?.highlights?.length ? (
                    <p className="rounded-xl border border-dashed border-line px-4 py-8 text-center text-sm text-ink-faint">
                      No highlights yet. In the full product, you'd highlight text in the PDF viewer above.
                    </p>
                  ) : (
                    <div className="flex flex-col gap-3">
                      {readingData.highlights.map((h) => (
                        <Card key={h.id} className="p-4 group relative">
                          <p className="mb-2 rounded-lg bg-teal-50 px-3 py-2 text-sm italic text-teal-800 border border-teal-100">
                            "{h.selected_text}"
                          </p>
                          {h.ai_note && (
                            <p className="text-sm text-ink mb-2 pl-2 border-l-2 border-line">{h.ai_note}</p>
                          )}
                          <div className="flex items-center justify-between text-xs text-ink-faint">
                            <span>{new Date(h.created_at).toLocaleString()}</span>
                            <button 
                              onClick={() => handleDeleteHighlight(h.id)}
                              className="opacity-0 group-hover:opacity-100 transition-opacity text-red-500 hover:text-red-700"
                            >
                              <Trash2 className="h-3.5 w-3.5" />
                            </button>
                          </div>
                        </Card>
                      ))}
                    </div>
                  )}
                </>
              )}
            </TabsContent>

            <TabsContent value="summary">
              <Card className="p-6">
                <p className="text-sm text-ink-soft italic">AI analysis not implemented in this MVP.</p>
              </Card>
            </TabsContent>

            <TabsContent value="extracted">
              <Card className="p-6">
                <p className="text-sm text-ink-soft italic">Information extraction not implemented in this MVP.</p>
              </Card>
            </TabsContent>

            <TabsContent value="related">
              <p className="mb-4 text-sm text-ink-soft">
                Papers SAIRA has identified as agreeing with or challenging this one's claims.
              </p>
              <RelatedPapersPanel links={[]} />
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
              <p className="text-sm text-ink-faint">Similar papers discovery is disabled in this MVP.</p>
            </div>
          </div>
        </div>
      </div>
      
      {/* Save to Project Dialog */}
      <Dialog open={isDialogOpen} onOpenChange={setIsDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Save to a project</DialogTitle>
            <DialogDescription>
              Choose which project should keep this paper.
            </DialogDescription>
          </DialogHeader>
          <div className="flex flex-col gap-2">
            {allProjects.filter(p => !paperProjects.some(pp => pp.id === p.id)).length === 0 ? (
              <p className="text-sm text-ink-faint text-center py-4">This paper is already in all your projects.</p>
            ) : (
              allProjects.filter(p => !paperProjects.some(pp => pp.id === p.id)).map((proj) => (
                <button
                  key={proj.id}
                  onClick={() => handleSaveToProject(proj.id)}
                  className="flex items-center justify-between rounded-xl border border-line px-4 py-3 text-left text-sm hover:border-teal-500 hover:bg-teal-50/40"
                >
                  <span className="font-medium text-ink">{proj.name}</span>
                </button>
              ))
            )}
          </div>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setIsDialogOpen(false)}>
              Cancel
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
      
      {/* Manual Highlight Dialog */}
      <Dialog open={isHighlightDialogOpen} onOpenChange={setIsHighlightDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Add Manual Highlight</DialogTitle>
            <DialogDescription>
              Since the PDF viewer isn't connected, you can paste text here to save a highlight.
            </DialogDescription>
          </DialogHeader>
          <div className="flex flex-col gap-4">
            <div className="flex flex-col gap-2">
              <label className="text-sm font-medium text-ink">Highlighted Text (Required)</label>
              <Textarea 
                value={draftHighlightText}
                onChange={e => setDraftHighlightText(e.target.value)}
                placeholder="Paste the text from the paper..."
              />
            </div>
            <div className="flex flex-col gap-2">
              <label className="text-sm font-medium text-ink">My Note (Optional)</label>
              <Textarea 
                value={draftHighlightNote}
                onChange={e => setDraftHighlightNote(e.target.value)}
                placeholder="Why did you highlight this?"
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setIsHighlightDialogOpen(false)}>
              Cancel
            </Button>
            <Button onClick={handleAddHighlight} disabled={!draftHighlightText.trim()}>
              Save Highlight
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
      
    </div>
  );
}
