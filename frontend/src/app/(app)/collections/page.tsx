"use client";

import { useState, useEffect } from "react";
import { Layers, Plus, Loader2 } from "lucide-react";
import { PageHeader } from "@/components/shared/page-header";
import { SearchBar } from "@/components/shared/search-bar";
import { CollectionCard } from "@/components/shared/collection-card";
import { EmptyState } from "@/components/shared/empty-state";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { getCollections, createCollection, Collection } from "@/lib/api/collections";

export default function CollectionsPage() {
  const [query, setQuery] = useState("");
  const [collections, setCollections] = useState<Collection[]>([]);
  const [loading, setLoading] = useState(true);
  const [isDialogOpen, setIsDialogOpen] = useState(false);
  const [newCollectionName, setNewCollectionName] = useState("");
  const [newCollectionDesc, setNewCollectionDesc] = useState("");
  const [isCreating, setIsCreating] = useState(false);

  useEffect(() => {
    getCollections()
      .then(setCollections)
      .finally(() => setLoading(false));
  }, []);

  const handleCreate = async () => {
    if (!newCollectionName.trim()) return;
    setIsCreating(true);
    try {
      const created = await createCollection({
        name: newCollectionName.trim(),
        description: newCollectionDesc.trim() || undefined,
        color: "teal",
      });
      setCollections([created, ...collections]);
      setIsDialogOpen(false);
      setNewCollectionName("");
      setNewCollectionDesc("");
    } catch (e) {
      console.error(e);
    } finally {
      setIsCreating(false);
    }
  };

  const filtered = collections.filter(
    (c) =>
      c.name.toLowerCase().includes(query.toLowerCase()) ||
      (c.description && c.description.toLowerCase().includes(query.toLowerCase()))
  );

  return (
    <div>
      <PageHeader
        title="Collections"
        subtitle="Lighter-weight groupings than projects — for favorites, smart lists, and quick references."
        actions={
          <Dialog open={isDialogOpen} onOpenChange={setIsDialogOpen}>
            <DialogTrigger asChild>
              <Button className="gap-2">
                <Plus className="h-4 w-4" />
                New Collection
              </Button>
            </DialogTrigger>
            <DialogContent className="sm:max-w-[425px]">
              <DialogHeader>
                <DialogTitle>Create Collection</DialogTitle>
                <DialogDescription>
                  Group papers together outside of your main workspaces.
                </DialogDescription>
              </DialogHeader>
              <div className="grid gap-4 py-4">
                <div className="grid gap-2">
                  <Label htmlFor="name">Name</Label>
                  <Input 
                    id="name" 
                    placeholder="e.g., Must Reads 2026" 
                    value={newCollectionName}
                    onChange={(e) => setNewCollectionName(e.target.value)}
                  />
                </div>
                <div className="grid gap-2">
                  <Label htmlFor="desc">Description</Label>
                  <Textarea 
                    id="desc" 
                    placeholder="Optional description" 
                    value={newCollectionDesc}
                    onChange={(e) => setNewCollectionDesc(e.target.value)}
                  />
                </div>
              </div>
              <DialogFooter>
                <Button variant="outline" onClick={() => setIsDialogOpen(false)} disabled={isCreating}>Cancel</Button>
                <Button onClick={handleCreate} disabled={!newCollectionName.trim() || isCreating}>
                  {isCreating ? <Loader2 className="h-4 w-4 animate-spin" /> : "Create"}
                </Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>
        }
      />

      <SearchBar value={query} onChange={setQuery} placeholder="Filter your collections…" className="max-w-md" />

      <div className="mt-6">
        {loading ? (
          <div className="flex h-32 items-center justify-center">
            <Loader2 className="h-6 w-6 animate-spin text-ink-faint" />
          </div>
        ) : filtered.length === 0 ? (
          <EmptyState
            icon={Layers}
            title={collections.length === 0 ? "No collections yet" : "No collections match"}
            description={collections.length === 0 ? "Create your first collection to start grouping papers." : "Try a different search term."}
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
