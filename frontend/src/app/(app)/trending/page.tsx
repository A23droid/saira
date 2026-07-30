"use client";

import { useState } from "react";
import { Flame } from "lucide-react";
import { PageHeader } from "@/components/shared/page-header";
import { PaperCard } from "@/components/shared/paper-card";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { getTrendingPapers } from "@/lib/mock-data";

export default function TrendingPage() {
  const trending = getTrendingPapers();
  const [savedIds, setSavedIds] = useState<Set<string>>(new Set());

  return (
    <div>
      <PageHeader
        title="Trending"
        subtitle="Papers gaining citation velocity across the sources SAIRA tracks this week."
      />

      <div className="flex flex-col gap-3">
        {trending.map(({ paper, entry }, i) => (
          <div key={paper.id} className="flex gap-3">
            <span className="mt-5 hidden h-7 w-7 shrink-0 items-center justify-center rounded-full border border-line bg-surface font-display text-xs text-ink-faint sm:flex">
              {i + 1}
            </span>
            <div className="flex-1">
              <PaperCard
                paper={paper}
                trendLabel={`+${entry.weeklyCitationDelta} this week`}
                saved={savedIds.has(paper.id)}
                onSave={() =>
                  setSavedIds((prev) => {
                    const next = new Set(prev);
                    next.has(paper.id) ? next.delete(paper.id) : next.add(paper.id);
                    return next;
                  })
                }
              />
              <p className="mt-2 flex items-center gap-1.5 pl-1 text-xs text-ink-faint">
                <Flame className="h-3 w-3 text-brass-600" />
                {entry.reason}
                <Badge variant="outline" className="ml-1 font-mono text-[10px]">
                  Trend score {entry.trendScore}
                </Badge>
              </p>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
