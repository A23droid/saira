"use client";

import Link from "next/link";
import { motion } from "framer-motion";
import { Calendar, User } from "lucide-react";
import { Project } from "@/lib/types";
import { Card } from "@/components/ui/card";

const colorMap: Record<Project["color"], string> = {
  teal: "bg-teal-600",
  brass: "bg-brass-600",
  ink: "bg-ink",
};

export function ProjectCard({ project }: { project: Project }) {
  // Gracefully handle color if it's missing or invalid from DB
  const colorClass = colorMap[project.color] || "bg-teal-600";
  const updatedDate = new Date(project.updated_at || project.created_at || "").toLocaleDateString();

  return (
    <motion.div initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.25 }}>
      <Link href={`/projects/${project.id}`}>
        <Card className="group flex h-full flex-col gap-4 p-6 transition-shadow hover:shadow-md">
          <div className="flex items-start justify-between gap-3">
            <div className={`h-2.5 w-2.5 rounded-full ${colorClass}`} />
            <span className="font-mono text-[11px] text-ink-faint flex items-center gap-1">
              <Calendar className="h-3 w-3" /> {updatedDate}
            </span>
          </div>

          <div>
            <h3 className="font-display text-lg font-medium leading-snug text-ink group-hover:text-teal-700">
              {project.name}
            </h3>
            <p className="mt-1.5 line-clamp-2 text-sm leading-relaxed text-ink-soft">
              {project.description || "No description provided."}
            </p>
          </div>

          <div className="mt-auto flex items-center justify-between border-t border-line-soft pt-4">
            <div className="flex items-center gap-1.5 text-xs text-ink-faint">
              <User className="h-3.5 w-3.5" />
              Personal Project
            </div>
          </div>
        </Card>
      </Link>
    </motion.div>
  );
}
