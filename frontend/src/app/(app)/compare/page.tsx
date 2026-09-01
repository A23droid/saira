"use client";

import { useState, useEffect } from "react";
import { GitCompareArrows, Loader2 } from "lucide-react";
import toast from "react-hot-toast";
import { PageHeader } from "@/components/shared/page-header";
import { SearchBar } from "@/components/shared/search-bar";
import { ComparePanel } from "@/components/shared/compare-panel";
import { EmptyState } from "@/components/shared/empty-state";
import { Checkbox } from "@/components/ui/checkbox";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { BackendPaper, getPapers } from "@/lib/api/papers";
import { generateComparison, Comparison } from "@/lib/api/comparisons";

export default function ComparePage() {
  const [query, setQuery] = useState("");
  const [selection, setSelection] = useState<string[]>([]);
  const [papers, setPapers] = useState<BackendPaper[]>([]);
  const [loading, setLoading] = useState(true);
  
  const [generating, setGenerating] = useState(false);
  const [comparison, setComparison] = useState<Comparison | null>(null);

  useEffect(() => {
    async function fetchPapers() {
      try {
        const data = await getPapers();
        setPapers(data);
      } catch (err) {
        console.error("Failed to fetch papers:", err);
      } finally {
        setLoading(false);
      }
    }
    fetchPapers();
  }, []);

  const filtered = papers.filter((p) => p.title.toLowerCase().includes(query.toLowerCase()));
  const selectedPapers = papers.filter((p) => selection.includes(p.id));

  async function handleGenerate() {
    if (selection.length < 2) return;
    setGenerating(true);
    setComparison(null);
    try {
      const title = `Comparison of ${selectedPapers.length} papers`;
      const res = await generateComparison(title, selection);
      setComparison(res);
    } catch (err) {
      console.error("Failed to generate comparison:", err);
      toast.error("Failed to generate comparison. Please try again.");
    } finally {
      setGenerating(false);
    }
  }

  return (
    <div>
      <PageHeader
        title="Compare papers"
        subtitle="Pick any papers from your library to line up side by side."
      />

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="lg:col-span-1">
          <SearchBar value={query} onChange={setQuery} placeholder="Find a paper to add…" />
          <div className="thin-scroll mt-4 flex max-h-[520px] flex-col gap-2 overflow-y-auto pr-1">
            {loading ? (
              <p className="p-4 text-center text-sm text-ink-faint">Loading papers...</p>
            ) : filtered.length === 0 ? (
               <p className="p-4 text-center text-sm text-ink-faint">No papers found.</p>
            ) : (
              filtered.map((p) => (
                <label
                  key={p.id}
                  className="flex items-start gap-3 rounded-xl border border-line bg-surface p-3.5 text-sm hover:border-teal-500/60"
                >
                  <Checkbox
                    className="mt-0.5"
                    checked={selection.includes(p.id)}
                    onCheckedChange={(checked) => {
                      setSelection((prev) =>
                        checked
                          ? prev.length < 5
                            ? [...prev, p.id]
                            : prev
                          : prev.filter((id) => id !== p.id)
                      );
                    }}
                  />
                  <span>
                    <span className="block leading-snug text-ink">{p.title}</span>
                    <span className="mt-1 flex items-center gap-1.5 text-xs text-ink-faint">
                      {p.publication_year || "Unknown"} <Badge variant="outline" className="font-mono text-[10px]">{p.source || "web"}</Badge>
                    </span>
                  </span>
                </label>
              ))
            )}
          </div>
          <p className="mt-3 text-xs text-ink-faint">Up to 5 papers · {selection.length} selected</p>
          
          <Button 
            className="mt-4 w-full" 
            disabled={selection.length < 2 || generating} 
            onClick={handleGenerate}
          >
            {generating ? <><Loader2 className="mr-2 h-4 w-4 animate-spin" /> Generating...</> : "Generate Comparison"}
          </Button>
        </div>

        <div className="lg:col-span-2">
          {selection.length < 2 ? (
            <EmptyState
              icon={GitCompareArrows}
              title="Select at least two papers"
              description="Check papers from the list to compare their methods, datasets, and results."
            />
          ) : generating ? (
            <div className="flex h-64 flex-col items-center justify-center space-y-4 rounded-xl border border-line-soft bg-surface">
              <Loader2 className="h-8 w-8 animate-spin text-teal-600" />
              <p className="text-sm text-ink-soft">Analyzing papers and generating comparison...</p>
            </div>
          ) : comparison ? (
            <ComparePanel
              papers={selectedPapers}
              comparison={comparison}
              onRemove={(id) => setSelection((prev) => prev.filter((p) => p !== id))}
            />
          ) : (
             <div className="flex h-64 flex-col items-center justify-center rounded-xl border border-line-soft bg-surface">
              <p className="text-sm text-ink-soft">Click 'Generate Comparison' to analyze selected papers.</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
