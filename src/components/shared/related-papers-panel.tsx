import Link from "next/link";
import { ThumbsUp, ThumbsDown } from "lucide-react";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Paper, RelatedPaperLink } from "@/lib/types";
import { EmptyState } from "@/components/shared/empty-state";

export function RelatedPapersPanel({
  links,
}: {
  links: { link: RelatedPaperLink; paper: Paper }[];
}) {
  const supporting = links.filter((l) => l.link.relation === "supports");
  const contradicting = links.filter((l) => l.link.relation === "contradicts");

  if (links.length === 0) {
    return (
      <EmptyState
        icon={ThumbsUp}
        title="No relationships mapped yet"
        description="SAIRA hasn't identified papers that clearly support or contradict this one yet."
      />
    );
  }

  return (
    <div className="grid gap-5 sm:grid-cols-2">
      <div>
        <div className="mb-3 flex items-center gap-2">
          <ThumbsUp className="h-4 w-4 text-teal-600" />
          <h3 className="text-sm font-medium text-ink">Supporting papers</h3>
        </div>
        <div className="flex flex-col gap-2.5">
          {supporting.length === 0 && (
            <p className="text-sm text-ink-faint">None identified yet.</p>
          )}
          {supporting.map(({ link, paper }) => (
            <RelatedRow key={paper.id} paper={paper} note={link.note} tone="supports" />
          ))}
        </div>
      </div>
      <div>
        <div className="mb-3 flex items-center gap-2">
          <ThumbsDown className="h-4 w-4 text-danger" />
          <h3 className="text-sm font-medium text-ink">Contradicting papers</h3>
        </div>
        <div className="flex flex-col gap-2.5">
          {contradicting.length === 0 && (
            <p className="text-sm text-ink-faint">None identified yet.</p>
          )}
          {contradicting.map(({ link, paper }) => (
            <RelatedRow key={paper.id} paper={paper} note={link.note} tone="contradicts" />
          ))}
        </div>
      </div>
    </div>
  );
}

function RelatedRow({
  paper,
  note,
  tone,
}: {
  paper: Paper;
  note: string;
  tone: "supports" | "contradicts";
}) {
  return (
    <Card className="p-4">
      <div className="flex items-start justify-between gap-2">
        <Link href={`/papers/${paper.id}`} className="text-sm font-medium leading-snug text-ink hover:text-teal-700">
          {paper.title}
        </Link>
        <Badge variant={tone === "supports" ? "secondary" : "danger"} className="shrink-0">
          {tone === "supports" ? "Supports" : "Contradicts"}
        </Badge>
      </div>
      <p className="mt-1.5 text-xs leading-relaxed text-ink-soft">{note}</p>
    </Card>
  );
}
