"use client";

import { useMemo, useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { SlidersHorizontal, Sparkles, SearchX, Loader2 } from "lucide-react";
import { PageHeader } from "@/components/shared/page-header";
import { SearchBar } from "@/components/shared/search-bar";
import { PaperCard } from "@/components/shared/paper-card";
import { EmptyState } from "@/components/shared/empty-state";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog";
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from "@/components/ui/select";
import { Project, Paper, PaperSource } from "@/lib/types";
import { getProjects } from "@/lib/api/projects";
import { searchPapersExternal, ingestPaper, OpenAlexSearchResult } from "@/lib/api/search";

const allSources: PaperSource[] = ["arXiv", "Semantic Scholar", "PubMed", "IEEE", "ACL Anthology", "OpenAlex"];
const suggestions = [
  "parameter-efficient fine-tuning",
  "retrieval-augmented generation",
  "chain-of-thought reasoning",
  "diffusion models",
];

// Helper to map search results to the expected UI type to preserve the layout
function mapToUIPaper(r: OpenAlexSearchResult): Paper {
  return {
    id: r.openalex_id || r.doi || r.title,
    title: r.title || "Untitled",
    authors: [],
    year: r.publication_year || new Date().getFullYear(),
    venue: r.venue || "Unknown Venue",
    source: (r.source as PaperSource) || "OpenAlex",
    abstract: r.abstract || "No abstract provided.",
    citationCount: r.citation_count || 0,
    tags: [],
    pdfUrl: r.pdf_url,
    savedToProjectIds: [],
    readingStatus: "unread",
    aiSummary: {
      tldr: "",
      keyFindings: [],
      methodology: "",
      limitations: []
    },
    extracted: {
      problem: "",
      dataset: [],
      method: "",
      metrics: [],
      codeAvailable: false
    }
  } as Paper;
}

export default function SearchPapersPage() {
  const router = useRouter();
  const [query, setQuery] = useState("");
  const [submittedQuery, setSubmittedQuery] = useState("");
  const [sourceFilter, setSourceFilter] = useState<string>("all");
  const [sortBy, setSortBy] = useState<string>("relevance");
  const [savedIds, setSavedIds] = useState<Set<string>>(new Set());
  const [pickerPaper, setPickerPaper] = useState<Paper | null>(null);
  
  const [searchResults, setSearchResults] = useState<Paper[]>([]);
  const [isSearching, setIsSearching] = useState(false);
  const [projects, setProjects] = useState<Project[]>([]);

  useEffect(() => {
    getProjects().then(setProjects).catch(console.error);
  }, []);

  useEffect(() => {
    if (!submittedQuery.trim()) {
      setSearchResults([]);
      return;
    }
    
    let active = true;
    setIsSearching(true);
    
    searchPapersExternal(submittedQuery, 20)
      .then((data) => {
        if (active) {
          setSearchResults(data.map(mapToUIPaper));
        }
      })
      .catch(console.error)
      .finally(() => {
        if (active) setIsSearching(false);
      });
      
    return () => { active = false; };
  }, [submittedQuery]);

  const results = useMemo(() => {
    let list = searchResults;
    
    if (sourceFilter !== "all") {
      list = list.filter((p) => p.source === sourceFilter);
    }
    if (sortBy === "year") {
      list = [...list].sort((a, b) => b.year - a.year);
    } else if (sortBy === "citations") {
      list = [...list].sort((a, b) => b.citationCount - a.citationCount);
    }
    return list;
  }, [searchResults, sourceFilter, sortBy]);

  const handleSaveToProject = async (projId: string) => {
    if (!pickerPaper || !pickerPaper.id) return;
    
    // In our mapped UI paper, 'id' is currently storing the openalex_id for this purpose
    const openalexId = pickerPaper.id;
    
    try {
      const res = await ingestPaper(openalexId, projId);
      setSavedIds((prev) => new Set(prev).add(openalexId));
      router.push(`/papers/${res.paper.id}`);
    } catch (err) {
      console.error("Failed to save paper", err);
    } finally {
      setPickerPaper(null);
    }
  };

  return (
    <div>
      <PageHeader
        title="Search papers"
        subtitle="Query OpenAlex and ingest papers into your projects."
      />

      <SearchBar
        value={query}
        onChange={setQuery}
        onSubmit={() => setSubmittedQuery(query)}
        placeholder="Try “retrieval-augmented generation” or an author name…"
      />

      {!submittedQuery && (
        <div className="mt-4 flex flex-wrap gap-2">
          {suggestions.map((s) => (
            <button
              key={s}
              onClick={() => {
                setQuery(s);
                setSubmittedQuery(s);
              }}
              className="rounded-full border border-line bg-surface px-3.5 py-1.5 text-xs font-medium text-ink-soft hover:border-teal-500 hover:text-teal-700"
            >
              {s}
            </button>
          ))}
        </div>
      )}

      <div className="mt-6 flex flex-wrap items-center gap-3">
        <div className="flex items-center gap-1.5 text-sm text-ink-faint">
          <SlidersHorizontal className="h-3.5 w-3.5" /> Filters
        </div>
        <Select value={sourceFilter} onValueChange={setSourceFilter}>
          <SelectTrigger className="w-44">
            <SelectValue placeholder="Source" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All sources</SelectItem>
            {allSources.map((s) => (
              <SelectItem key={s} value={s}>
                {s}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Select value={sortBy} onValueChange={setSortBy}>
          <SelectTrigger className="w-44">
            <SelectValue placeholder="Sort by" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="relevance">Sort: Relevance</SelectItem>
            <SelectItem value="year">Sort: Newest</SelectItem>
            <SelectItem value="citations">Sort: Most cited</SelectItem>
          </SelectContent>
        </Select>

        <div className="ml-auto flex items-center gap-1.5 text-xs text-ink-faint">
          {isSearching ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Sparkles className="h-3.5 w-3.5 text-teal-600" />}
          {isSearching ? "Searching..." : `${results.length} results`}
        </div>
      </div>

      <div className="mt-5 flex flex-col gap-3">
        {results.length === 0 && !isSearching && submittedQuery ? (
          <EmptyState
            icon={SearchX}
            title="No papers matched"
            description="Try a different keyword."
            actionLabel="Clear search"
            onAction={() => {
              setQuery("");
              setSubmittedQuery("");
              setSourceFilter("all");
            }}
          />
        ) : (
          results.map((p) => (
            <PaperCard
              key={p.id}
              paper={p}
              saved={savedIds.has(p.id)}
              onSave={() => setPickerPaper(p)}
            />
          ))
        )}
      </div>

      <Dialog open={!!pickerPaper} onOpenChange={(o) => !o && setPickerPaper(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Save to a project</DialogTitle>
            <DialogDescription>
              Choose which project should keep {pickerPaper?.title.slice(0, 40)}
              {pickerPaper && pickerPaper.title.length > 40 ? "…" : ""}
            </DialogDescription>
          </DialogHeader>
          <div className="flex flex-col gap-2">
            {projects.length === 0 && (
              <p className="text-sm text-ink-faint text-center py-4">No projects yet. Create one first.</p>
            )}
            {projects.map((proj) => (
              <button
                key={proj.id}
                onClick={() => handleSaveToProject(proj.id)}
                className="flex items-center justify-between rounded-xl border border-line px-4 py-3 text-left text-sm hover:border-teal-500 hover:bg-teal-50/40"
              >
                <span className="font-medium text-ink">{proj.name}</span>
                <Badge variant="outline" className="capitalize">{proj.color || "teal"}</Badge>
              </button>
            ))}
          </div>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setPickerPaper(null)}>
              Cancel
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
