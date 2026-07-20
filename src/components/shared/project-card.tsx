"use client";

import Link from "next/link";
import { motion } from "framer-motion";
import { FileStack, Users } from "lucide-react";
import { Project } from "@/lib/types";
import { Card } from "@/components/ui/card";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";

const colorMap: Record<Project["color"], string> = {
  teal: "bg-teal-600",
  brass: "bg-brass-600",
  ink: "bg-ink",
};

export function ProjectCard({ project }: { project: Project }) {
  const milestoneCount = Object.values(project.milestones).filter(Boolean).length;

  return (
    <motion.div initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.25 }}>
      <Link href={`/projects/${project.id}`}>
        <Card className="group flex h-full flex-col gap-4 p-6 transition-shadow hover:shadow-md">
          <div className="flex items-start justify-between gap-3">
            <div className={`h-2.5 w-2.5 rounded-full ${colorMap[project.color]}`} />
            <span className="font-mono text-[11px] text-ink-faint">
              {milestoneCount}/4 waypoints
            </span>
          </div>

          <div>
            <h3 className="font-display text-lg font-medium leading-snug text-ink group-hover:text-teal-700">
              {project.name}
            </h3>
            <p className="mt-1.5 line-clamp-2 text-sm leading-relaxed text-ink-soft">
              {project.description}
            </p>
          </div>

          <div className="mt-auto flex items-center justify-between border-t border-line-soft pt-4">
            <div className="flex items-center gap-1.5 text-xs text-ink-faint">
              <FileStack className="h-3.5 w-3.5" />
              {project.paperIds.length} papers
            </div>
            <div className="flex items-center gap-2">
              <div className="flex -space-x-2">
                {project.collaborators.slice(0, 3).map((c) => (
                  <Avatar key={c.name} className="h-6 w-6 border-2 border-surface">
                    <AvatarFallback className="text-[10px]">{c.avatarInitial}</AvatarFallback>
                  </Avatar>
                ))}
              </div>
              {project.collaborators.length > 1 && (
                <span className="flex items-center gap-1 text-xs text-ink-faint">
                  <Users className="h-3 w-3" />
                  {project.collaborators.length}
                </span>
              )}
            </div>
          </div>
        </Card>
      </Link>
    </motion.div>
  );
}
