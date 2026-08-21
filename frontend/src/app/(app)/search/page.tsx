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
import { getProjects, updateProjectPaper } from "@/lib/api/projects";
import { searchPapersExternal, ingestPaper, OpenAlexSearchResult, SearchSource } from "@/lib/api/search";

const availableSources: { value: SearchSource; label: string }[] = [
  { value: "openalex", label: "OpenAlex" },
  { value: "arxiv", label: "arXiv" },
  { value: "semantic_scholar", label: "Semantic Scholar" },
];
const suggestions = [
  "parameter-efficient fine-tuning",
  "retrieval-augmented generation",
  "chain-of-thought reasoning",
  "diffusion models",
];

// Helper to map search results to the expected UI type to preserve the layout
function mapToUIPaper(r: OpenAlexSearchResult): Paper & { _raw: OpenAlexSearchResult } {
  return {
    id: r.openalex_id || r.arxiv_id || r.semantic_scholar_id || r.doi || r.title,
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
    },
    _raw: r,
  } as Paper & { _raw: OpenAlexSearchResult };
}

export default function SearchPapersPage() {
  const router = useRouter();
  const [query, setQuery] = useState("");
  const [submittedQuery, setSubmittedQuery] = useState("");
  const [sourceFilter, setSourceFilter] = useState<SearchSource>("openalex");
  const [page, setPage] = useState(1);
  const [sortBy, setSortBy] = useState<string>("relevance");
  const [savedIds, setSavedIds] = useState<Set<string>>(new Set());
  const [pickerPaper, setPickerPaper] = useState<(Paper & { _raw: OpenAlexSearchResult }) | null>(null);
  const [selectedProjectIdForSave, setSelectedProjectIdForSave] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);
  const [saveAction, setSaveAction] = useState<"save" | "favorite">("save");
  
  const [searchResults, setSearchResults] = useState<(Paper & { _raw: OpenAlexSearchResult })[]>([]);
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
    
    searchPapersExternal(submittedQuery, 20, page, sourceFilter)
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
  }, [submittedQuery, sourceFilter, page]);

  const results = useMemo(() => {
    let list = searchResults;
    
    // The API already filtered by source, but we keep this here just in case of 'all'
    if (sourceFilter !== "all" && list.some(p => p.source && p.source.toLowerCase() !== sourceFilter.replace("_", " "))) {
      // no-op, let the backend filtering take precedence
    }
    if (sortBy === "year") {
      list = [...list].sort((a, b) => b.year - a.year);
    } else if (sortBy === "citations") {
      list = [...list].sort((a, b) => b.citationCount - a.citationCount);
    }
    return list;
  }, [searchResults, sourceFilter, sortBy]);

  const handleSaveToProject = async () => {
    if (!pickerPaper || !pickerPaper.id || !pickerPaper._raw || !selectedProjectIdForSave) return;
    
    const uiId = pickerPaper.id;
    const r = pickerPaper._raw;
    
    setIsSaving(true);
    try {
      const res = await ingestPaper(
        { 
          openalex_id: r.openalex_id || undefined, 
          arxiv_id: r.arxiv_id || undefined, 
          semantic_scholar_id: r.semantic_scholar_id || undefined 
        }, 
        selectedProjectIdForSave
      );
      if (saveAction === "favorite") {
        await updateProjectPaper(selectedProjectIdForSave, res.paper.id, { favorite: true });
      }
      setSavedIds((prev) => new Set(prev).add(uiId));
      router.push(`/papers/${res.paper.id}`);
    } catch (err) {
      console.error("Failed to save paper", err);
      alert("Failed to save paper. Please try again.");
    } finally {
      setIsSaving(false);
      setPickerPaper(null);
      setSelectedProjectIdForSave(null);
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
        isLoading={isSearching}
        onSubmit={() => {
          setPage(1);
          setSubmittedQuery(query);
        }}
        placeholder="Try “retrieval-augmented generation” or an author name…"
      />

      {!submittedQuery && (
        <div className="mt-4 flex flex-wrap gap-2">
          {suggestions.map((s) => (
            <button
              key={s}
              onClick={() => {
                setQuery(s);
                setPage(1);
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
        <Select value={sourceFilter} onValueChange={(val) => { setPage(1); setSourceFilter(val as SearchSource); }}>
          <SelectTrigger className="w-44">
            <SelectValue placeholder="Source" />
          </SelectTrigger>
          <SelectContent>
            {availableSources.map((s) => (
              <SelectItem key={s.value} value={s.value}>
                {s.label}
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
              setPage(1);
              setSourceFilter("openalex");
            }}
          />
        ) : (
          results.map((p) => (
            <PaperCard
              key={p.id}
              paper={p}
              saved={savedIds.has(p.id)}
              onFavorite={() => {
                setSaveAction("favorite");
                setPickerPaper(p);
              }}
              onSave={() => {
                setSaveAction("save");
                setPickerPaper(p);
              }}
              disableLink
            />
          ))
        )}
      </div>

      {submittedQuery && results.length > 0 && (
        <div className="mt-8 flex items-center justify-center gap-4">
          <Button 
            variant="outline" 
            size="sm" 
            disabled={page <= 1 || isSearching}
            onClick={() => setPage(p => Math.max(1, p - 1))}
          >
            Previous
          </Button>
          <span className="text-sm text-ink-faint">Page {page}</span>
          <Button 
            variant="outline" 
            size="sm"
            disabled={results.length < 20 || isSearching}
            onClick={() => setPage(p => p + 1)}
          >
            Next
          </Button>
        </div>
      )}

      <Dialog open={!!pickerPaper} onOpenChange={(o) => {
        if (!o) {
          setPickerPaper(null);
          setSelectedProjectIdForSave(null);
        }
      }}>
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
                onClick={() => setSelectedProjectIdForSave(proj.id)}
                className={`flex items-center justify-between rounded-xl border px-4 py-3 text-left text-sm transition-colors ${
                  selectedProjectIdForSave === proj.id
                    ? "border-teal-600 bg-teal-50/40"
                    : "border-line hover:border-teal-500 hover:bg-teal-50/20"
                }`}
              >
                <span className={`font-medium ${selectedProjectIdForSave === proj.id ? "text-teal-900" : "text-ink"}`}>
                  {proj.name}
                </span>
                <Badge variant={selectedProjectIdForSave === proj.id ? "default" : "outline"} className="capitalize">
                  {proj.color || "teal"}
                </Badge>
              </button>
            ))}
          </div>
          <DialogFooter>
            <Button variant="ghost" onClick={() => {
              setPickerPaper(null);
              setSelectedProjectIdForSave(null);
            }}>
              Cancel
            </Button>
            <Button 
              onClick={handleSaveToProject} 
              disabled={!selectedProjectIdForSave || isSaving}
              className="gap-2"
            >
              {isSaving && <Loader2 className="h-4 w-4 animate-spin" />}
              {isSaving ? "Saving..." : "Save"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
