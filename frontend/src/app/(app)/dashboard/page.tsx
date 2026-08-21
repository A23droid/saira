"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import { FileStack, FolderKanban, NotebookPen, Sparkles, ArrowRight, Plus } from "lucide-react";
import { PageHeader } from "@/components/shared/page-header";
import { StatCard } from "@/components/shared/stat-card";
import { ProjectCard } from "@/components/shared/project-card";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { useAuth } from "@/contexts/auth-context";
import { Project } from "@/lib/types";
import { getProjects } from "@/lib/api/projects";
import { getPapers } from "@/lib/api/papers";

export default function DashboardPage() {
  const { user } = useAuth();
  const [projects, setProjects] = useState<Project[]>([]);
  const [paperCount, setPaperCount] = useState<number | null>(null);
  const firstName = user?.name.split(" ")[0] ?? "there";

  useEffect(() => {
    getProjects()
      .then((data) => {
        const sorted = [...data].sort((a, b) =>
          (a.updated_at < b.updated_at ? 1 : -1)
        );
        setProjects(sorted);
      })
      .catch(console.error);
    getPapers(0, 1000)
      .then((data) => setPaperCount(data.length))
      .catch(console.error);
  }, []);

  const recentProjects = projects.slice(0, 3);
  const firstProject = projects[0];

  return (
    <div>
      <PageHeader
        title={`Welcome back, ${firstName}`}
        subtitle="Here's where your research trail left off."
        actions={
          <Link href="/search">
            <Button variant="outline" className="gap-1.5">
              <Plus className="h-3.5 w-3.5" />
              Find papers
            </Button>
          </Link>
        }
      />

      <div className="grid gap-4 sm:grid-cols-3">
        <StatCard icon={FolderKanban} label="Active projects" value={String(projects.length)} />
        <StatCard icon={FileStack} label="Papers saved" value={paperCount !== null ? String(paperCount) : "—"} accent="brass" />
        <StatCard icon={NotebookPen} label="Notes written" value="—" />
      </div>

      <div className="mt-10 flex items-center justify-between">
        <h2 className="font-display text-xl font-medium text-ink">Continue a project</h2>
        <Link href="/projects" className="flex items-center gap-1 text-sm font-medium text-teal-700 hover:underline">
          View all <ArrowRight className="h-3.5 w-3.5" />
        </Link>
      </div>
      <div className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {recentProjects.length === 0 ? (
          <p className="text-sm text-ink-faint col-span-3">No projects yet. <Link href="/projects/new" className="underline text-teal-700">Create one to get started.</Link></p>
        ) : (
          recentProjects.map((p) => (
            <ProjectCard key={p.id} project={p} />
          ))
        )}
      </div>

      <Card className="mt-10 flex flex-col gap-4 p-6 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-3">
          <span className="flex h-10 w-10 items-center justify-center rounded-full bg-teal-50">
            <Sparkles className="h-4.5 w-4.5 text-teal-600" />
          </span>
          <div>
            <p className="font-medium text-ink">Ask SAIRA anything</p>
            <p className="text-sm text-ink-soft">
              Open a project chat to ask questions across all your saved papers.
            </p>
          </div>
        </div>
        {firstProject ? (
          <Link href={`/projects/${firstProject.id}?tab=chat`}>
            <Button className="gap-1.5">
              Ask a question <ArrowRight className="h-3.5 w-3.5" />
            </Button>
          </Link>
        ) : (
          <Link href="/projects/new">
            <Button variant="outline" className="gap-1.5">
              Create a project first <ArrowRight className="h-3.5 w-3.5" />
            </Button>
          </Link>
        )}
      </Card>

      {user && (
        <div className="mt-10 flex items-center gap-3 rounded-2xl border border-line-soft bg-paper-dim/40 p-5">
          <Avatar className="h-9 w-9 border border-line">
            <AvatarFallback>{user.avatarInitial}</AvatarFallback>
          </Avatar>
          <p className="text-sm text-ink-soft">
            Signed in as <span className="font-medium text-ink">{user.email}</span>
          </p>
        </div>
      )}
    </div>
  );
}
