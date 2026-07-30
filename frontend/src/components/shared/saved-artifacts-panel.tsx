import Link from "next/link";
import { Sparkles, FileText, MessageSquareQuote } from "lucide-react";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { EmptyState } from "@/components/shared/empty-state";
import { SavedArtifact } from "@/lib/types";
import { getPaperById } from "@/lib/mock-data";

export function SavedArtifactsPanel({ artifacts }: { artifacts: SavedArtifact[] }) {
  if (artifacts.length === 0) {
    return (
      <EmptyState
        icon={Sparkles}
        title="No saved artifacts yet"
        description="Pin an Ask AI answer or a literature review snippet to keep it handy here."
      />
    );
  }

  return (
    <div className="flex flex-col gap-3">
      {artifacts.map((a) => (
        <Card key={a.id} className="p-5">
          <div className="mb-2 flex items-center justify-between gap-3">
            <div className="flex items-center gap-2">
              <span className="flex h-7 w-7 items-center justify-center rounded-full bg-teal-50">
                {a.type === "chat_answer" ? (
                  <MessageSquareQuote className="h-3.5 w-3.5 text-teal-600" />
                ) : (
                  <FileText className="h-3.5 w-3.5 text-teal-600" />
                )}
              </span>
              <p className="text-sm font-medium text-ink">{a.title}</p>
            </div>
            <Badge variant="outline">{a.type === "chat_answer" ? "Chat answer" : "Review snippet"}</Badge>
          </div>
          <p className="text-sm leading-relaxed text-ink-soft">{a.content}</p>
          {a.citedPaperIds && a.citedPaperIds.length > 0 && (
            <div className="mt-3 flex flex-wrap gap-1.5">
              {a.citedPaperIds.map((id) => {
                const paper = getPaperById(id);
                if (!paper) return null;
                return (
                  <Link key={id} href={`/papers/${id}`}>
                    <Badge variant="secondary" className="cursor-pointer">
                      {paper.title.length > 30 ? paper.title.slice(0, 30) + "…" : paper.title}
                    </Badge>
                  </Link>
                );
              })}
            </div>
          )}
          <p className="mt-3 text-xs text-ink-faint">Saved {a.createdAt}</p>
        </Card>
      ))}
    </div>
  );
}
