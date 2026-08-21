"use client";

import Link from "next/link";
import { motion } from "framer-motion";
import { BookmarkPlus, Quote, FileCheck2, Flame, Star } from "lucide-react";
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
}: {
  paper: Paper;
  onSave?: (paper: Paper) => void;
  saved?: boolean;
  compact?: boolean;
  /** Optional trend callout, e.g. "+412 citations this week" — used on the Trending page. */
  trendLabel?: string;
  /** When true, the title is not a link (e.g. un-ingested search results that have no DB UUID). */
  disableLink?: boolean;
  onFavorite?: (paper: Paper) => void;
  favorited?: boolean;
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
          {paper.authors.map((a) => a.name).join(", ")} &middot; {paper.venue}
        </p>

        {!compact && (
          <p className="line-clamp-2 text-sm leading-relaxed text-ink-soft">{paper.abstract}</p>
        )}

        <div className="flex flex-wrap items-center gap-1.5 pt-1">
          {paper.tags.slice(0, 3).map((tag) => (
            <Badge key={tag} variant="secondary">
              {tag}
            </Badge>
          ))}
        </div>

        <div className="mt-1 flex items-center justify-between border-t border-line-soft pt-3">
          <div className="flex items-center gap-4 text-xs text-ink-faint">
            <span className="flex items-center gap-1">
              <Quote className="h-3.5 w-3.5" /> {paper.citationCount.toLocaleString()}
            </span>
            <span className="flex items-center gap-1">
              <FileCheck2 className="h-3.5 w-3.5" /> {statusCopy[paper.readingStatus]}
            </span>
            <span className="hidden font-mono sm:inline">{paper.source}</span>
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
