"use client";

import { use } from "react";
import { notFound } from "next/navigation";
import { Star, Clock, Flame, Layers, Sparkles, FileStack } from "lucide-react";
import { PageHeader } from "@/components/shared/page-header";
import { PaperCard } from "@/components/shared/paper-card";
import { EmptyState } from "@/components/shared/empty-state";
import { Badge } from "@/components/ui/badge";
import { getCollectionById, getPapersForCollection } from "@/lib/mock-data";
import { CollectionIcon } from "@/lib/types";

const iconMap: Record<CollectionIcon, typeof Star> = {
  star: Star,
  clock: Clock,
  flame: Flame,
  layers: Layers,
};

export default function CollectionDetailsPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const collection = getCollectionById(id);

  if (!collection) return notFound();

  const collectionPapers = getPapersForCollection(collection.id);
  const Icon = iconMap[collection.icon];

  return (
    <div>
      <PageHeader
        title={collection.name}
        subtitle={collection.description}
        actions={
          collection.smart ? (
            <Badge variant="outline" className="gap-1">
              <Sparkles className="h-3 w-3" /> Smart collection
            </Badge>
          ) : undefined
        }
      />

      <div className="mb-6 flex items-center gap-4">
        <span className="flex h-10 w-10 items-center justify-center rounded-full bg-teal-50 text-teal-600">
          <Icon className="h-4.5 w-4.5" />
        </span>
        <div className="flex items-center gap-1.5 text-sm text-ink-faint">
          <FileStack className="h-3.5 w-3.5" />
          {collectionPapers.length} papers · updated {collection.updatedAt}
        </div>
      </div>

      {collectionPapers.length === 0 ? (
        <EmptyState
          icon={Layers}
          title="This collection is empty"
          description="Save papers from search results into this collection to see them here."
        />
      ) : (
        <div className="flex flex-col gap-3">
          {collectionPapers.map((p) => (
            <PaperCard key={p.id} paper={p} />
          ))}
        </div>
      )}
    </div>
  );
}
