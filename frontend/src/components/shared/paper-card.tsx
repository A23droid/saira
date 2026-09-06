"use client";

import type { ReactNode } from "react";
import Link from "next/link";
import { motion } from "framer-motion";
import { BookmarkPlus, Quote, FileCheck2, Flame, Star, Layers } from "lucide-react";
import { Paper } from "@/lib/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";

const statusCopy: Record<Paper["readingStatus"], string> = {
  unread: "Unread",
  reading: "Reading",
  read: "Read",
};

export function PaperCard({
  paper,
  onSave,
  saved,
  compact = false,
  trendLabel,
  disableLink = false,
  onFavorite,
  favorited,
  onOpen,
  onAddToCollection,
  statusSlot,
}: {
  paper: Paper;
  onSave?: (paper: Paper) => void;
  onAddToCollection?: (paper: Paper) => void;
  saved?: boolean;
  compact?: boolean;
  /** Optional trend callout, e.g. "+412 citations this week" — used on the Trending page. */
  trendLabel?: string;
  /** When true, the title is not a link (e.g. un-ingested search results that have no DB UUID). */
  disableLink?: boolean;
  /** When provided, the title acts as a button triggering this callback. */
  onOpen?: (paper: Paper) => void;
  onFavorite?: (paper: Paper) => void;
  favorited?: boolean;
  /** Rendered under the metadata line — used to show live indexing progress after saving. */
  statusSlot?: ReactNode;
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25 }}
    >
      <Card className="group flex flex-col gap-3 p-5 transition-shadow hover:shadow-md">
        <div className="flex items-start justify-between gap-3">
          {disableLink ? (
            <h3 className="font-display text-[1.05rem] font-medium leading-snug text-ink min-w-0">
              {paper.title}
            </h3>
          ) : onOpen ? (
            <button onClick={() => onOpen(paper)} className="min-w-0 text-left cursor-pointer">
              <h3 className="font-display text-[1.05rem] font-medium leading-snug text-ink group-hover:text-teal-700">
                {paper.title}
              </h3>
            </button>
          ) : (
            <Link href={`/papers/${paper.id}`} className="min-w-0">
              <h3 className="font-display text-[1.05rem] font-medium leading-snug text-ink group-hover:text-teal-700">
                {paper.title}
              </h3>
            </Link>
          )}
          <div className="flex shrink-0 items-center gap-1.5">
            {trendLabel && (
              <Badge variant="brass" className="gap-1">
                <Flame className="h-3 w-3" /> {trendLabel}
              </Badge>
            )}
            <Badge variant="outline" className="font-mono text-[11px]">
              {paper.year}
            </Badge>
          </div>
        </div>

        <p className="truncate text-sm text-ink-soft">
          {paper.authors?.map((a) => a.name).join(", ") || "Unknown authors"} &middot; {paper.venue}
        </p>

        {!compact && (
          <p className="line-clamp-2 text-sm leading-relaxed text-ink-soft">{paper.abstract}</p>
        )}

        <div className="flex flex-wrap items-center gap-1.5 pt-1">
          {(paper.tags || []).slice(0, 3).map((tag) => (
            <Badge key={tag} variant="secondary">
              {tag}
            </Badge>
          ))}
        </div>

        {statusSlot}

        <div className="mt-1 flex items-center justify-between border-t border-line-soft pt-3">
          <div className="flex items-center gap-4 text-xs text-ink-faint">
            <span className="flex items-center gap-1">
              <Quote className="h-3.5 w-3.5" /> {(paper.citationCount ?? 0).toLocaleString()}
            </span>
            <span className="flex items-center gap-1">
              <FileCheck2 className="h-3.5 w-3.5" /> {statusCopy[paper.readingStatus]}
            </span>
            <span className="hidden font-mono sm:inline">{paper.source}</span>
            {paper.pdfUrl && (
              <span className="flex items-center gap-1 text-teal-700 font-medium">
                <FileCheck2 className="h-3.5 w-3.5" /> PDF
              </span>
            )}
          </div>
          <div className="flex items-center gap-2">
            {onFavorite && (
              <Button
                variant="ghost"
                size="sm"
                onClick={() => onFavorite(paper)}
                className={`gap-1.5 ${favorited ? "text-teal-600" : ""}`}
              >
                <Star className={`h-3.5 w-3.5 ${favorited ? "fill-teal-600 text-teal-600" : "text-ink-faint"}`} />
                {favorited ? "Favorited" : "Favorite"}
              </Button>
            )}
            {onAddToCollection && (
              <Button
                variant="ghost"
                size="sm"
                onClick={() => onAddToCollection(paper)}
                className="gap-1.5"
              >
                <Layers className="h-3.5 w-3.5" />
                Add to Collection
              </Button>
            )}
            {onSave && (
              <Button
                variant={saved ? "secondary" : "ghost"}
                size="sm"
                onClick={() => onSave(paper)}
                className="gap-1.5"
              >
                <BookmarkPlus className="h-3.5 w-3.5" />
                {saved ? "Saved" : "Save"}
              </Button>
            )}
          </div>
        </div>
      </Card>
    </motion.div>
  );
}
