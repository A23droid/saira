"use client";

import { X } from "lucide-react";
import { BackendPaper } from "@/lib/api/papers";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { BookmarkPlus, Check } from "lucide-react";
import { useState } from "react";
import { createSavedArtifact } from "@/lib/api/projects";
import toast from "react-hot-toast";

export function ComparePanel({
  papers,
  comparison,
  onRemove,
  projectId,
}: {
  papers: BackendPaper[];
  comparison: Comparison;
  onRemove?: (id: string) => void;
  projectId?: string;
}) {
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  const handleSave = async () => {
    if (!projectId || saving || saved) return;
    setSaving(true);
    try {
      await createSavedArtifact(projectId, {
        type: "review_snippet",
        title: `Comparison Takeaway: ${comparison.content.dimensions.map(d => d.name).slice(0,2).join(", ")}`,
        content: comparison.content.research_takeaway,
        citedPaperIds: comparison.paper_ids
      });
      setSaved(true);
      toast.success("Saved to artifacts");
    } catch (e) {
      console.error(e);
      toast.error("Failed to save artifact");
    } finally {
      setSaving(false);
    }
  };

  if (papers.length === 0 || !comparison) return null;

  // The generated comparison papers might be ordered differently than the selected papers.
  // The prompt says "in the same order as provided". We will trust the order of `selection` matches `comparison.paper_ids`.
  // To be perfectly safe, we map dimensions to the paper order based on index.
  
  // Sort the papers array to match the order in comparison.paper_ids
  const orderedPapers = comparison.paper_ids
    .map(id => papers.find(p => p.id === id))
    .filter((p): p is BackendPaper => p !== undefined);
    
  if (orderedPapers.length === 0) return null;

  return (
    <div className="space-y-6">
      <Card className="overflow-x-auto">
        <table className="w-full min-w-[560px] border-collapse text-sm">
          <thead>
            <tr>
              <th className="w-40 border-b border-line-soft bg-paper-dim/50 p-4 text-left text-xs font-medium uppercase tracking-wide text-ink-faint">
                Dimension
              </th>
              {orderedPapers.map((p) => (
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
                    {p.publication_year || "Unknown"}
                  </p>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {comparison.content.dimensions.map((dim, idx) => (
              <tr key={idx} className="odd:bg-paper-dim/20">
                <td className="border-b border-line-soft p-4 text-xs font-medium uppercase tracking-wide text-ink-faint align-top">
                  {dim.name}
                </td>
                {orderedPapers.map((p, pIdx) => (
                  <td key={p.id} className="border-b border-line-soft p-4 align-top text-ink">
                    {dim.values[pIdx] || "—"}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </Card>

      <div className="grid gap-6 md:grid-cols-2">
        <Card className="border-line-soft bg-surface shadow-none">
          <CardHeader className="p-4 pb-2">
            <CardTitle className="text-sm font-medium uppercase tracking-wide text-ink-faint">Commonalities</CardTitle>
          </CardHeader>
          <CardContent className="p-4 pt-0">
            {comparison.content.commonalities.length > 0 ? (
              <ul className="list-disc space-y-1.5 pl-4 text-sm text-ink-soft">
                {comparison.content.commonalities.map((c, i) => (
                  <li key={i}>{c}</li>
                ))}
              </ul>
            ) : (
              <p className="text-sm text-ink-faint">None noted.</p>
            )}
          </CardContent>
        </Card>

        <Card className="border-line-soft bg-surface shadow-none">
          <CardHeader className="p-4 pb-2">
            <CardTitle className="text-sm font-medium uppercase tracking-wide text-ink-faint">Key Differences</CardTitle>
          </CardHeader>
          <CardContent className="p-4 pt-0">
            {comparison.content.key_differences.length > 0 ? (
              <ul className="list-disc space-y-1.5 pl-4 text-sm text-ink-soft">
                {comparison.content.key_differences.map((d, i) => (
                  <li key={i}>{d}</li>
                ))}
              </ul>
            ) : (
              <p className="text-sm text-ink-faint">None noted.</p>
            )}
          </CardContent>
        </Card>
      </div>
      
      <Card className="border-teal-100 bg-teal-50/30 shadow-none relative group">
        <CardHeader className="p-4 pb-2 flex flex-row items-center justify-between">
          <CardTitle className="text-sm font-medium uppercase tracking-wide text-teal-800">Research Takeaway</CardTitle>
          {projectId && (
            <div className="opacity-0 group-hover:opacity-100 transition-opacity">
              <Button
                variant="ghost"
                size="sm"
                className="h-6 text-[10px] text-teal-800 hover:text-teal-900 gap-1 px-2"
                onClick={handleSave}
                disabled={saving || saved}
              >
                {saved ? <Check className="h-3 w-3 text-green-600" /> : <BookmarkPlus className="h-3 w-3" />}
                {saved ? "Saved" : "Save to artifacts"}
              </Button>
            </div>
          )}
        </CardHeader>
        <CardContent className="p-4 pt-0">
          <p className="text-sm leading-relaxed text-teal-900">{comparison.content.research_takeaway}</p>
        </CardContent>
      </Card>
      
      {comparison.content.overall_summary && (
        <Card className="border-line-soft bg-surface shadow-none">
          <CardHeader className="p-4 pb-2">
            <CardTitle className="text-sm font-medium uppercase tracking-wide text-ink-faint">Overall Summary</CardTitle>
          </CardHeader>
          <CardContent className="p-4 pt-0">
            <p className="text-sm leading-relaxed text-ink-soft">{comparison.content.overall_summary}</p>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
