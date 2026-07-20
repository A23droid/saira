"use client";

import { useState } from "react";
import { GitCompareArrows } from "lucide-react";
import { PageHeader } from "@/components/shared/page-header";
import { SearchBar } from "@/components/shared/search-bar";
import { ComparePanel } from "@/components/shared/compare-panel";
import { EmptyState } from "@/components/shared/empty-state";
import { Checkbox } from "@/components/ui/checkbox";
import { Badge } from "@/components/ui/badge";
import { papers } from "@/lib/mock-data";

export default function ComparePage() {
  const [query, setQuery] = useState("");
  const [selection, setSelection] = useState<string[]>(["p1", "p4"]);

  const filtered = papers.filter((p) => p.title.toLowerCase().includes(query.toLowerCase()));
  const selectedPapers = papers.filter((p) => selection.includes(p.id));

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
            {filtered.map((p) => (
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
                        ? prev.length < 4
                          ? [...prev, p.id]
                          : prev
                        : prev.filter((id) => id !== p.id)
                    );
                  }}
                />
                <span>
                  <span className="block leading-snug text-ink">{p.title}</span>
                  <span className="mt-1 flex items-center gap-1.5 text-xs text-ink-faint">
                    {p.year} <Badge variant="outline" className="font-mono text-[10px]">{p.source}</Badge>
                  </span>
                </span>
              </label>
            ))}
          </div>
          <p className="mt-3 text-xs text-ink-faint">Up to 4 papers · {selection.length} selected</p>
        </div>

        <div className="lg:col-span-2">
          {selectedPapers.length < 2 ? (
            <EmptyState
              icon={GitCompareArrows}
              title="Select at least two papers"
              description="Check papers from the list to compare their methods, datasets, and results."
            />
          ) : (
            <ComparePanel
              papers={selectedPapers}
              onRemove={(id) => setSelection((prev) => prev.filter((p) => p !== id))}
            />
          )}
        </div>
      </div>
    </div>
  );
}
