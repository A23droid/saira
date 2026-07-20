"use client";

import { useState } from "react";
import Link from "next/link";
import { Plus, FolderKanban } from "lucide-react";
import { PageHeader } from "@/components/shared/page-header";
import { ProjectCard } from "@/components/shared/project-card";
import { EmptyState } from "@/components/shared/empty-state";
import { SearchBar } from "@/components/shared/search-bar";
import { Button } from "@/components/ui/button";
import { projects } from "@/lib/mock-data";

export default function ProjectsListPage() {
  const [query, setQuery] = useState("");

  const filtered = projects.filter(
    (p) =>
      p.name.toLowerCase().includes(query.toLowerCase()) ||
      p.description.toLowerCase().includes(query.toLowerCase())
  );

  return (
    <div>
      <PageHeader
        title="Projects"
        subtitle="Each project keeps its own papers, notes, and generated review."
        actions={
          <Link href="/projects/new">
            <Button className="gap-1.5">
              <Plus className="h-3.5 w-3.5" />
              New project
            </Button>
          </Link>
        }
      />

      <SearchBar value={query} onChange={setQuery} placeholder="Filter your projects…" className="max-w-md" />

      <div className="mt-6">
        {filtered.length === 0 ? (
          <EmptyState
            icon={FolderKanban}
            title="No projects match"
            description="Try a different search term, or start a new project to begin a fresh trail."
            actionLabel="New project"
            onAction={() => (window.location.href = "/projects/new")}
          />
        ) : (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {filtered.map((p) => (
              <ProjectCard key={p.id} project={p} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
