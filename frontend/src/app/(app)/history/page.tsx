"use client";

import { useMemo, useState } from "react";
import { History as HistoryIcon } from "lucide-react";
import { PageHeader } from "@/components/shared/page-header";
import { HistoryTimeline } from "@/components/shared/history-timeline";
import { EmptyState } from "@/components/shared/empty-state";
import { Card } from "@/components/ui/card";
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from "@/components/ui/select";
import { historyEvents } from "@/lib/mock-data";
import { HistoryEventType } from "@/lib/types";

const typeLabels: Record<HistoryEventType | "all", string> = {
  all: "All activity",
  search: "Searches",
  view_paper: "Papers viewed",
  view_project: "Projects viewed",
  chat: "Ask AI",
  compare: "Comparisons",
  review_generated: "Reviews generated",
  note_added: "Notes",
};

export default function HistoryPage() {
  const [filter, setFilter] = useState<string>("all");

  const filtered = useMemo(() => {
    const sorted = [...historyEvents].sort((a, b) => (a.timestamp < b.timestamp ? 1 : -1));
    if (filter === "all") return sorted;
    return sorted.filter((e) => e.type === filter);
  }, [filter]);

  return (
    <div className="mx-auto max-w-2xl">
      <PageHeader title="History" subtitle="Everything you've searched, read, and asked SAIRA, in one trail." />

      <div className="mb-6 flex items-center gap-3">
        <Select value={filter} onValueChange={setFilter}>
          <SelectTrigger className="w-56">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {Object.entries(typeLabels).map(([value, label]) => (
              <SelectItem key={value} value={value}>
                {label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <Card className="p-6">
        {filtered.length === 0 ? (
          <EmptyState
            icon={HistoryIcon}
            title="No activity of this type yet"
            description="Try a different filter to see more of your history."
          />
        ) : (
          <HistoryTimeline events={filtered} />
        )}
      </Card>
    </div>
  );
}
