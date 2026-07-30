"use client";

import { useState } from "react";
import { PageHeader } from "@/components/shared/page-header";
import { LiteratureReviewPanel } from "@/components/shared/literature-review-panel";
import { Card } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from "@/components/ui/select";
import { papers, projects } from "@/lib/mock-data";

export default function ReviewGeneratorPage() {
  const [projectId, setProjectId] = useState<string>(projects[0].id);
  const [topic, setTopic] = useState(projects[0].name.toLowerCase());
  const [selection, setSelection] = useState<string[]>(
    projects[0].paperIds
  );

  const selectedPapers = papers.filter((p) => selection.includes(p.id));

  return (
    <div>
      <PageHeader
        title="Literature review generator"
        subtitle="Choose a set of papers and let SAIRA draft a structured first pass."
      />

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="flex flex-col gap-5 lg:col-span-1">
          <Card className="p-5">
            <div className="flex flex-col gap-1.5">
              <Label>Start from a project</Label>
              <Select
                value={projectId}
                onValueChange={(v) => {
                  setProjectId(v);
                  const proj = projects.find((p) => p.id === v)!;
                  setSelection(proj.paperIds);
                  setTopic(proj.name.toLowerCase());
                }}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {projects.map((p) => (
                    <SelectItem key={p.id} value={p.id}>
                      {p.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="mt-4 flex flex-col gap-1.5">
              <Label htmlFor="topic">Review topic</Label>
              <Input id="topic" value={topic} onChange={(e) => setTopic(e.target.value)} />
            </div>
          </Card>

          <Card className="p-5">
            <p className="mb-3 text-sm font-medium text-ink">Papers to include</p>
            <div className="flex flex-col gap-2">
              {papers.map((p) => (
                <label key={p.id} className="flex items-start gap-2.5 text-sm">
                  <Checkbox
                    className="mt-0.5"
                    checked={selection.includes(p.id)}
                    onCheckedChange={(checked) =>
                      setSelection((prev) =>
                        checked ? [...prev, p.id] : prev.filter((id) => id !== p.id)
                      )
                    }
                  />
                  <span className="leading-snug text-ink-soft">{p.title}</span>
                </label>
              ))}
            </div>
          </Card>
        </div>

        <div className="lg:col-span-2">
          <LiteratureReviewPanel key={selection.join(",")} papers={selectedPapers} topic={topic} />
        </div>
      </div>
    </div>
  );
}
