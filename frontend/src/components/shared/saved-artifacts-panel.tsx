import Link from "next/link";
import { Sparkles, FileText, MessageSquareQuote, Trash2 } from "lucide-react";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/shared/empty-state";
import { SavedArtifact } from "@/lib/types";
import { getPaperById } from "@/lib/api/papers";
import { deleteSavedArtifact } from "@/lib/api/projects";
import { useState, useEffect } from "react";
import toast from "react-hot-toast";

export function SavedArtifactsPanel({ artifacts: initialArtifacts }: { artifacts: SavedArtifact[] }) {
  const [artifacts, setArtifacts] = useState(initialArtifacts);
  
  // Keep state in sync if prop changes
  useEffect(() => {
    setArtifacts(initialArtifacts);
  }, [initialArtifacts]);
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
        <Card key={a.id} className="p-5 relative group">
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
            <div className="flex items-center gap-2">
              <Badge variant="outline">{a.type === "chat_answer" ? "Chat answer" : "Review snippet"}</Badge>
              <Button
                variant="ghost"
                size="icon"
                className="h-7 w-7 text-ink-faint hover:text-red-600 hover:bg-red-50 opacity-0 group-hover:opacity-100 transition-opacity ml-2"
                onClick={async () => {
                  if (!a.projectId || !confirm("Delete this artifact?")) return;
                  try {
                    await deleteSavedArtifact(a.projectId, a.id);
                    setArtifacts(prev => prev.filter(x => x.id !== a.id));
                    toast.success("Artifact deleted");
                  } catch (e) {
                    console.error("Failed to delete artifact", e);
                    toast.error("Failed to delete artifact");
                  }
                }}
              >
                <Trash2 className="h-3.5 w-3.5" />
              </Button>
            </div>
          </div>
          <p className="text-sm leading-relaxed text-ink-soft whitespace-pre-line">{a.content}</p>
          {a.citedPaperIds && a.citedPaperIds.length > 0 && (
            <div className="mt-3 flex flex-wrap gap-1.5">
              {a.citedPaperIds.map((id) => (
                <Link key={id} href={`/papers/${id}`}>
                  <Badge variant="secondary" className="cursor-pointer">
                    View cited paper
                  </Badge>
                </Link>
              ))}
            </div>
          )}
          <p className="mt-3 text-xs text-ink-faint">Saved {new Date(a.createdAt).toLocaleDateString()}</p>
        </Card>
      ))}
    </div>
  );
}
