"use client";

import { PageHeader } from "@/components/shared/page-header";
import { EmptyState } from "@/components/shared/empty-state";
import { Sparkles } from "lucide-react";

export default function ReviewGeneratorPage() {
  return (
    <div>
      <PageHeader
        title="Literature review generator"
        subtitle="Choose a set of papers and let SAIRA draft a structured first pass."
      />
      <div className="mt-8">
        <EmptyState
          icon={Sparkles}
          title="Milestone 4 Feature"
          description="The Literature Review Generator is an advanced AI functionality that is currently being built for Milestone 4 and is not available in the current MVP."
        />
      </div>
    </div>
  );
}
