"use client";

import { X } from "lucide-react";
import { Paper } from "@/lib/types";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";

const rows: { label: string; render: (p: Paper) => React.ReactNode }[] = [
  { label: "Year", render: (p) => p.year },
  { label: "Venue", render: (p) => p.venue },
  {
    label: "Problem",
    render: (p) => <span className="text-ink-soft">{p.extracted.problem}</span>,
  },
  { label: "Method", render: (p) => p.extracted.method },
  {
    label: "Datasets",
    render: (p) =>
      p.extracted.dataset.length ? (
        <div className="flex flex-wrap gap-1">
          {p.extracted.dataset.map((d) => (
            <Badge key={d} variant="secondary">
              {d}
            </Badge>
          ))}
        </div>
      ) : (
        <span className="text-ink-faint">—</span>
      ),
  },
  {
    label: "Reported metrics",
    render: (p) =>
      p.extracted.metrics.length ? (
        <ul className="space-y-1">
          {p.extracted.metrics.map((m) => (
            <li key={m.name} className="font-mono text-xs">
              {m.name}: <span className="text-teal-700">{m.value}</span>
            </li>
          ))}
        </ul>
      ) : (
        <span className="text-ink-faint">—</span>
      ),
  },
  {
    label: "Code available",
    render: (p) => (p.extracted.codeAvailable ? "Yes" : "No"),
  },
  { label: "Citations", render: (p) => p.citationCount.toLocaleString() },
];

export function ComparePanel({
  papers,
  onRemove,
}: {
  papers: Paper[];
  onRemove?: (id: string) => void;
}) {
  if (papers.length === 0) return null;

  return (
    <Card className="overflow-x-auto">
      <table className="w-full min-w-[560px] border-collapse text-sm">
        <thead>
          <tr>
            <th className="w-40 border-b border-line-soft bg-paper-dim/50 p-4 text-left text-xs font-medium uppercase tracking-wide text-ink-faint">
              Paper
            </th>
            {papers.map((p) => (
              <th key={p.id} className="min-w-[220px] border-b border-line-soft p-4 text-left align-top">
                <div className="flex items-start justify-between gap-2">
                  <p className="font-display text-[0.95rem] font-medium leading-snug text-ink">
                    {p.title}
                  </p>
                  {onRemove && (
                    <button
                      onClick={() => onRemove(p.id)}
                      className="shrink-0 rounded-full p-1 text-ink-faint hover:bg-paper-dim hover:text-ink"
                      aria-label={`Remove ${p.title}`}
                    >
                      <X className="h-3.5 w-3.5" />
                    </button>
                  )}
                </div>
                <p className="mt-1 text-xs text-ink-faint">
                  {p.authors[0]?.name}
                  {p.authors.length > 1 ? " et al." : ""}
                </p>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.label} className="odd:bg-paper-dim/20">
              <td className="border-b border-line-soft p-4 text-xs font-medium uppercase tracking-wide text-ink-faint">
                {row.label}
              </td>
              {papers.map((p) => (
                <td key={p.id} className="border-b border-line-soft p-4 align-top text-ink">
                  {row.render(p)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </Card>
  );
}
