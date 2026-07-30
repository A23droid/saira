"use client";

import { useState } from "react";
import { Layers } from "lucide-react";
import { PageHeader } from "@/components/shared/page-header";
import { SearchBar } from "@/components/shared/search-bar";
import { CollectionCard } from "@/components/shared/collection-card";
import { EmptyState } from "@/components/shared/empty-state";
import { collections } from "@/lib/mock-data";

export default function CollectionsPage() {
  const [query, setQuery] = useState("");

  const filtered = collections.filter(
    (c) =>
      c.name.toLowerCase().includes(query.toLowerCase()) ||
      c.description.toLowerCase().includes(query.toLowerCase())
  );

  return (
    <div>
      <PageHeader
        title="Collections"
        subtitle="Lighter-weight groupings than projects — for favorites, smart lists, and quick references."
      />

      <SearchBar value={query} onChange={setQuery} placeholder="Filter your collections…" className="max-w-md" />

      <div className="mt-6">
        {filtered.length === 0 ? (
          <EmptyState
            icon={Layers}
            title="No collections match"
            description="Try a different search term. Collections are curated automatically by SAIRA or by hand."
          />
        ) : (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {filtered.map((c) => (
              <CollectionCard key={c.id} collection={c} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
