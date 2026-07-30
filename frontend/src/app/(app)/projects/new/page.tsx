"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowRight, FolderPlus } from "lucide-react";
import { PageHeader } from "@/components/shared/page-header";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

const colorOptions = [
  { id: "teal", label: "Teal", className: "bg-teal-600" },
  { id: "brass", label: "Brass", className: "bg-brass-600" },
  { id: "ink", label: "Ink", className: "bg-ink" },
] as const;

export default function CreateProjectPage() {
  const router = useRouter();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [color, setColor] = useState<"teal" | "brass" | "ink">("teal");
  const [creating, setCreating] = useState(false);

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setCreating(true);
    setTimeout(() => {
      // Mock creation — in the full product this would POST and redirect to the new id.
      router.push("/projects/proj1");
    }, 600);
  }

  return (
    <div className="mx-auto max-w-xl">
      <PageHeader title="New project" subtitle="Give your research trail a name and a starting point." />

      <Card className="p-7">
        <form onSubmit={handleSubmit} className="flex flex-col gap-5">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="project-name">Project name</Label>
            <Input
              id="project-name"
              placeholder="e.g. Efficient Fine-Tuning Methods"
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
            />
          </div>

          <div className="flex flex-col gap-1.5">
            <Label htmlFor="project-desc">Description</Label>
            <Textarea
              id="project-desc"
              placeholder="What is this project trying to answer?"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={4}
            />
          </div>

          <div className="flex flex-col gap-2">
            <Label>Color tag</Label>
            <div className="flex gap-3">
              {colorOptions.map((c) => (
                <button
                  type="button"
                  key={c.id}
                  onClick={() => setColor(c.id)}
                  className={cn(
                    "flex h-9 w-9 items-center justify-center rounded-full border-2 transition-all",
                    color === c.id ? "border-ink scale-105" : "border-transparent"
                  )}
                  aria-label={c.label}
                >
                  <span className={cn("h-5 w-5 rounded-full", c.className)} />
                </button>
              ))}
            </div>
          </div>

          <div className="mt-2 flex items-center gap-3 rounded-xl border border-line-soft bg-paper-dim/40 px-4 py-3">
            <FolderPlus className="h-4 w-4 shrink-0 text-teal-600" />
            <p className="text-xs leading-relaxed text-ink-soft">
              You can add papers, take notes, compare sources, and generate a literature review once
              the project is created.
            </p>
          </div>

          <div className="mt-2 flex justify-end gap-2">
            <Button type="button" variant="ghost" onClick={() => router.push("/projects")}>
              Cancel
            </Button>
            <Button type="submit" disabled={!name.trim() || creating} className="gap-1.5">
              {creating ? "Creating…" : "Create project"}
              {!creating && <ArrowRight className="h-3.5 w-3.5" />}
            </Button>
          </div>
        </form>
      </Card>
    </div>
  );
}
