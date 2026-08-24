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
import { getCollections, addPaperToCollection, Collection } from "@/lib/api/collections";

const availableSources: { value: SearchSource; label: string }[] = [
  { value: "all", label: "All sources" },
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

function mapToUIPaper(r: OpenAlexSearchResult): Paper & { _raw: OpenAlexSearchResult; ui_id: string } {
  const ui_id = r.local_id || r.openalex_id || r.arxiv_id || r.semantic_scholar_id || r.doi || r.title || Math.random().toString();
  return {
    id: r.local_id || "",
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
    ui_id,
  } as Paper & { _raw: OpenAlexSearchResult; ui_id: string };
}

export default function SearchPapersPage() {
  const router = useRouter();
  const [query, setQuery] = useState("");
  const [submittedQuery, setSubmittedQuery] = useState("");
  const [sourceFilter, setSourceFilter] = useState<SearchSource>("all");
  const [page, setPage] = useState(1);
  const [sortBy, setSortBy] = useState<string>("relevance");
  const [savedIds, setSavedIds] = useState<Set<string>>(new Set());
  const [searchResults, setSearchResults] = useState<(Paper & { _raw: OpenAlexSearchResult; ui_id: string })[]>([]);
  const [isSearching, setIsSearching] = useState(false);
  const [isOpening, setIsOpening] = useState(false);
  const [projects, setProjects] = useState<Project[]>([]);
  const [collections, setCollections] = useState<Collection[]>([]);
  const [pickerPaper, setPickerPaper] = useState<(Paper & { _raw: OpenAlexSearchResult; ui_id: string }) | null>(null);
  const [selectedProjectIdForSave, setSelectedProjectIdForSave] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);
  const [saveAction, setSaveAction] = useState<"save" | "favorite">("save");
  const [collectionPickerPaper, setCollectionPickerPaper] = useState<(Paper & { _raw: OpenAlexSearchResult; ui_id: string }) | null>(null);
  const [selectedCollectionIdForSave, setSelectedCollectionIdForSave] = useState<string | null>(null);

  useEffect(() => {
    getProjects().then(setProjects).catch(console.error);
    getCollections().then(setCollections).catch(console.error);
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

  const handleOpenPaper = async (p: Paper & { _raw: OpenAlexSearchResult }) => {
    if (p.id) {
      router.push(`/papers/${p.id}`);
      return;
    }
    
    setIsOpening(true);
    try {
      const res = await ingestPaper({
        openalex_id: p._raw.openalex_id || undefined,
        arxiv_id: p._raw.arxiv_id || undefined,
        semantic_scholar_id: p._raw.semantic_scholar_id || undefined
      });
      router.push(`/papers/${res.paper.id}`);
    } catch (e) {
      console.error(e);
      alert("Failed to open paper");
    } finally {
      setIsOpening(false);
    }
  };

  const handleSaveToProject = async () => {
    if (!pickerPaper || !pickerPaper._raw || !selectedProjectIdForSave) return;

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
      setSavedIds((prev) => new Set(prev).add(pickerPaper.ui_id));
      router.push(`/papers/${res.paper.id}`);
    } catch (e) {
      console.error(e);
      alert("Failed to save paper");
    } finally {
      setIsSaving(false);
      setPickerPaper(null);
      setSelectedProjectIdForSave(null);
    }
  };

  const handleSaveToCollection = async () => {
    if (!collectionPickerPaper || !collectionPickerPaper._raw || !selectedCollectionIdForSave) return;

    const r = collectionPickerPaper._raw;

    setIsSaving(true);
    try {
      // First ingest to our DB
      const res = await ingestPaper({
        openalex_id: r.openalex_id || undefined,
        arxiv_id: r.arxiv_id || undefined,
        semantic_scholar_id: r.semantic_scholar_id || undefined
      });
      // Then link to collection
      await addPaperToCollection(selectedCollectionIdForSave, res.paper.id);
      setCollectionPickerPaper(null);
      setSelectedCollectionIdForSave(null);
    } catch (e) {
      console.error(e);
      alert("Failed to add paper to collection");
    } finally {
      setIsSaving(false);
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
              setSourceFilter("all");
            }}
          />
        ) : (
          <>
            {results.map((p) => (
              <PaperCard
                key={p.ui_id}
                paper={p}
                saved={savedIds.has(p.ui_id)}
                onFavorite={() => {
                  setSaveAction("favorite");
                  setPickerPaper(p);
                  setSelectedProjectIdForSave(null);
                }}
                onSave={() => {
                  setSaveAction("save");
                  setPickerPaper(p);
                  setSelectedProjectIdForSave(null);
                }}
                onAddToCollection={() => {
                  setCollectionPickerPaper(p);
                  setSelectedCollectionIdForSave(null);
                }}
                onOpen={() => handleOpenPaper(p)}
                disableLink={false}
              />
            ))}
            {results.length > 0 && (
              <div className="mt-4 flex items-center justify-between border-t border-line pt-4">
                <Button
                  variant="outline"
                  size="sm"
                  disabled={page <= 1 || isSearching}
                  onClick={() => {
                    setPage(p => Math.max(1, p - 1));
                    window.scrollTo({ top: 0, behavior: 'smooth' });
                  }}
                >
                  Previous
                </Button>
                <span className="text-sm text-ink-faint">Page {page}</span>
                <Button
                  variant="outline"
                  size="sm"
                  disabled={results.length < 20 || isSearching}
                  onClick={() => {
                    setPage(p => p + 1);
                    window.scrollTo({ top: 0, behavior: 'smooth' });
                  }}
                >
                  Next
                </Button>
              </div>
            )}
            {/* )} */}
          </>
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
            {projects.map((proj) => {
              const isAlreadySaved = pickerPaper?._raw.saved_project_ids?.includes(proj.id);
              
              return (
                <button
                  key={proj.id}
                  disabled={isAlreadySaved}
                  onClick={() => setSelectedProjectIdForSave(proj.id)}
                  className={`flex items-center justify-between rounded-xl border px-4 py-3 text-left text-sm transition-colors ${
                    isAlreadySaved 
                      ? "border-line-soft bg-paper-dim opacity-50 cursor-not-allowed"
                      : selectedProjectIdForSave === proj.id
                        ? "border-teal-600 bg-teal-50/40"
                        : "border-line hover:border-teal-500 hover:bg-teal-50/20"
                    }`}
                >
                  <span className={`font-medium ${selectedProjectIdForSave === proj.id ? "text-teal-900" : "text-ink"}`}>
                    {proj.name}
                  </span>
                  <Badge variant={selectedProjectIdForSave === proj.id ? "default" : "outline"} className="capitalize">
                    {isAlreadySaved ? "Already saved" : proj.color || "teal"}
                  </Badge>
                </button>
              );
            })}
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

      <Dialog open={!!collectionPickerPaper} onOpenChange={(o) => {
        if (!o) {
          setCollectionPickerPaper(null);
          setSelectedCollectionIdForSave(null);
        }
      }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Add to a collection</DialogTitle>
            <DialogDescription>
              Choose which collection should keep {collectionPickerPaper?.title.slice(0, 40)}
              {collectionPickerPaper && collectionPickerPaper.title.length > 40 ? "…" : ""}
            </DialogDescription>
          </DialogHeader>
          <div className="flex flex-col gap-2">
            {collections.length === 0 && (
              <p className="text-sm text-ink-faint text-center py-4">No collections yet. Create one in the Collections page.</p>
            )}
            {collections.map((col) => (
              <button
                key={col.id}
                onClick={() => setSelectedCollectionIdForSave(col.id)}
                className={`flex items-center justify-between rounded-xl border px-4 py-3 text-left text-sm transition-colors ${selectedCollectionIdForSave === col.id
                    ? "border-teal-600 bg-teal-50/40"
                    : "border-line hover:border-teal-500 hover:bg-teal-50/20"
                  }`}
              >
                <span className={`font-medium ${selectedCollectionIdForSave === col.id ? "text-teal-900" : "text-ink"}`}>
                  {col.name}
                </span>
                <Badge variant={selectedCollectionIdForSave === col.id ? "default" : "outline"} className="capitalize">
                  {col.color || "teal"}
                </Badge>
              </button>
            ))}
          </div>
          <DialogFooter>
            <Button variant="ghost" onClick={() => {
              setCollectionPickerPaper(null);
              setSelectedCollectionIdForSave(null);
            }}>
              Cancel
            </Button>
            <Button
              onClick={handleSaveToCollection}
              disabled={!selectedCollectionIdForSave || isSaving}
              className="gap-2"
            >
              {isSaving && <Loader2 className="h-4 w-4 animate-spin" />}
              {isSaving ? "Adding..." : "Add"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
