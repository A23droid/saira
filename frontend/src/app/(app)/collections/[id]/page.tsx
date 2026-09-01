"use client";

import { useState, useEffect } from "react";
import { use } from "react";
import { notFound } from "next/navigation";
import { Layers, FileStack, Loader2 } from "lucide-react";
import { PageHeader } from "@/components/shared/page-header";
import { PaperCard } from "@/components/shared/paper-card";
import { EmptyState } from "@/components/shared/empty-state";
import { getCollection, getCollectionPapers, Collection } from "@/lib/api/collections";
import { Paper } from "@/lib/types";

export default function CollectionDetailsPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  
  const [collection, setCollection] = useState<Collection | null>(null);
  const [papers, setPapers] = useState<Paper[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      getCollection(id),
      getCollectionPapers(id)
    ])
      .then(([col, paps]) => {
        setCollection(col);
        setPapers(paps);
      })
      .catch((err) => {
        console.error(err);
      })
      .finally(() => setLoading(false));
  }, [id]);

  if (loading) {
    return (
      <div className="flex h-[50vh] items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-ink-faint" />
      </div>
    );
  }

  if (!collection) return notFound();

  return (
    <div>
      <PageHeader
        title={collection.name}
        subtitle={collection.description || undefined}
      />

      <div className="mb-6 flex items-center gap-4">
        <span className="flex h-10 w-10 items-center justify-center rounded-full bg-teal-50 text-teal-600">
          <Layers className="h-4.5 w-4.5" />
        </span>
        <div className="flex items-center gap-1.5 text-sm text-ink-faint">
          <FileStack className="h-3.5 w-3.5" />
          {papers.length} papers · updated {new Date(collection.updated_at).toLocaleDateString()}
        </div>
      </div>

      {papers.length === 0 ? (
        <EmptyState
          icon={Layers}
          title="This collection is empty"
          description="Save papers from search results into this collection to see them here."
        />
      ) : (
        <div className="flex flex-col gap-3">
          {papers.map((p) => (
            <PaperCard key={p.id} paper={p} disableLink={false} />
          ))}
        </div>
      )}
    </div>
  );
}
