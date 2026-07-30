"use client";

import { useMemo, useState } from "react";
import { SlidersHorizontal, Sparkles, SearchX } from "lucide-react";
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
import { papers, projects } from "@/lib/mock-data";
import { Paper, PaperSource } from "@/lib/types";

const allSources: PaperSource[] = ["arXiv", "Semantic Scholar", "PubMed", "IEEE", "ACL Anthology"];
const suggestions = [
  "parameter-efficient fine-tuning",
  "retrieval-augmented generation",
  "chain-of-thought reasoning",
  "diffusion models",
];

export default function SearchPapersPage() {
  const [query, setQuery] = useState("");
  const [submittedQuery, setSubmittedQuery] = useState("");
  const [sourceFilter, setSourceFilter] = useState<string>("all");
  const [sortBy, setSortBy] = useState<string>("relevance");
  const [savedIds, setSavedIds] = useState<Set<string>>(new Set(["p1", "p2", "p4"]));
  const [pickerPaper, setPickerPaper] = useState<Paper | null>(null);

  const results = useMemo(() => {
    let list = papers;
    if (submittedQuery.trim()) {
      const q = submittedQuery.toLowerCase();
      list = list.filter(
        (p) =>
          p.title.toLowerCase().includes(q) ||
          p.tags.some((t) => t.toLowerCase().includes(q)) ||
          p.abstract.toLowerCase().includes(q)
      );
    }
    if (sourceFilter !== "all") {
      list = list.filter((p) => p.source === sourceFilter);
    }
    if (sortBy === "year") {
      list = [...list].sort((a, b) => b.year - a.year);
    } else if (sortBy === "citations") {
      list = [...list].sort((a, b) => b.citationCount - a.citationCount);
    }
    return list;
  }, [submittedQuery, sourceFilter, sortBy]);

  return (
    <div>
      <PageHeader
        title="Search papers"
        subtitle="Query arXiv, Semantic Scholar, PubMed, and more from one place."
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
          <Sparkles className="h-3.5 w-3.5 text-teal-600" />
          {results.length} results
        </div>
      </div>

      <div className="mt-5 flex flex-col gap-3">
        {results.length === 0 ? (
          <EmptyState
            icon={SearchX}
            title="No papers matched"
            description="Try a different keyword, or clear your filters to see the full mock library."
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
            {projects.map((proj) => (
              <button
                key={proj.id}
                onClick={() => {
                  if (pickerPaper) {
                    setSavedIds((prev) => new Set(prev).add(pickerPaper.id));
                  }
                  setPickerPaper(null);
                }}
                className="flex items-center justify-between rounded-xl border border-line px-4 py-3 text-left text-sm hover:border-teal-500 hover:bg-teal-50/40"
              >
                <span className="font-medium text-ink">{proj.name}</span>
                <Badge variant="outline">{proj.paperIds.length} papers</Badge>
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
