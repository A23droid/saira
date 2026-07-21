"use client";

import Link from "next/link";
import { motion } from "framer-motion";
import { Star, Clock, Flame, Layers, FileStack, Sparkles } from "lucide-react";
import { Collection, CollectionIcon } from "@/lib/types";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

const iconMap: Record<CollectionIcon, typeof Star> = {
  star: Star,
  clock: Clock,
  flame: Flame,
  layers: Layers,
};

const colorMap: Record<Collection["color"], string> = {
  teal: "bg-teal-50 text-teal-600",
  brass: "bg-brass-100 text-brass-600",
  ink: "bg-paper-dim text-ink-soft",
};

export function CollectionCard({ collection }: { collection: Collection }) {
  const Icon = iconMap[collection.icon];

  return (
    <motion.div initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.25 }}>
      <Link href={`/collections/${collection.id}`}>
        <Card className="group flex h-full flex-col gap-4 p-6 transition-shadow hover:shadow-md">
          <div className="flex items-start justify-between gap-3">
            <span className={`flex h-9 w-9 items-center justify-center rounded-full ${colorMap[collection.color]}`}>
              <Icon className="h-4 w-4" />
            </span>
            {collection.smart && (
              <Badge variant="outline" className="gap-1">
                <Sparkles className="h-3 w-3" /> Smart
              </Badge>
            )}
          </div>

          <div>
            <h3 className="font-display text-lg font-medium leading-snug text-ink group-hover:text-teal-700">
              {collection.name}
            </h3>
            <p className="mt-1.5 line-clamp-2 text-sm leading-relaxed text-ink-soft">
              {collection.description}
            </p>
          </div>

          <div className="mt-auto flex items-center gap-1.5 border-t border-line-soft pt-4 text-xs text-ink-faint">
            <FileStack className="h-3.5 w-3.5" />
            {collection.paperIds.length} papers
          </div>
        </Card>
      </Link>
    </motion.div>
  );
}
