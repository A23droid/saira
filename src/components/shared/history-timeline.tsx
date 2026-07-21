import Link from "next/link";
import {
  Search,
  FileText,
  FolderKanban,
  Sparkles,
  GitCompareArrows,
  BookMarked,
  NotebookPen,
  LucideIcon,
} from "lucide-react";
import { HistoryEvent, HistoryEventType } from "@/lib/types";

const iconByType: Record<HistoryEventType, LucideIcon> = {
  search: Search,
  view_paper: FileText,
  view_project: FolderKanban,
  chat: Sparkles,
  compare: GitCompareArrows,
  review_generated: BookMarked,
  note_added: NotebookPen,
};

function formatTimestamp(iso: string) {
  const date = new Date(iso);
  return date.toLocaleDateString(undefined, { month: "short", day: "numeric" }) +
    " · " +
    date.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
}

export function HistoryTimeline({ events }: { events: HistoryEvent[] }) {
  return (
    <div className="flex flex-col">
      {events.map((event, i) => {
        const Icon = iconByType[event.type];
        const isLast = i === events.length - 1;
        const content = (
          <div className="flex gap-4">
            <div className="flex flex-col items-center">
              <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-line bg-surface">
                <Icon className="h-3.5 w-3.5 text-teal-600" />
              </span>
              {!isLast && <div className="trail-line-v flex-1" />}
            </div>
            <div className="pb-7">
              <p className="text-sm font-medium leading-snug text-ink">{event.title}</p>
              {event.detail && <p className="mt-1 text-sm text-ink-soft">{event.detail}</p>}
              <p className="mt-1.5 text-xs text-ink-faint">{formatTimestamp(event.timestamp)}</p>
            </div>
          </div>
        );

        return event.href ? (
          <Link key={event.id} href={event.href} className="rounded-xl hover:bg-paper-dim/40">
            {content}
          </Link>
        ) : (
          <div key={event.id}>{content}</div>
        );
      })}
    </div>
  );
}
