"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { Loader2, ArrowLeft } from "lucide-react";
import { PageHeader } from "@/components/shared/page-header";
import { ComparePanel } from "@/components/shared/compare-panel";
import { Button } from "@/components/ui/button";
import { BackendPaper, getPapers } from "@/lib/api/papers";
import { getComparison, Comparison } from "@/lib/api/comparisons";

export default function SavedComparisonPage() {
  const params = useParams();
  const router = useRouter();
  const id = params.id as string;

  const [loading, setLoading] = useState(true);
  const [comparison, setComparison] = useState<Comparison | null>(null);
  const [papers, setPapers] = useState<BackendPaper[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function fetchData() {
      try {
        const [compData, papersData] = await Promise.all([
          getComparison(id),
          getPapers(),
        ]);
        setComparison(compData);
        setPapers(papersData);
      } catch (err) {
        console.error(err);
        setError("Failed to load comparison.");
      } finally {
        setLoading(false);
      }
    }
    fetchData();
  }, [id]);

  if (loading) {
    return (
      <div className="flex h-[60vh] items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-teal-600" />
      </div>
    );
  }

  if (error || !comparison) {
    return (
      <div className="flex flex-col items-center justify-center space-y-4 pt-24">
        <p className="text-ink-soft">{error || "Comparison not found."}</p>
        <Button variant="outline" onClick={() => router.push("/compare")}>
          Back to Compare
        </Button>
      </div>
    );
  }

  const selectedPapers = comparison.paper_ids
    .map((pid) => papers.find((p) => p.id === pid))
    .filter((p): p is BackendPaper => p !== undefined);

  return (
    <div>
      <div className="mb-4">
        <Button variant="ghost" onClick={() => router.push("/compare")} className="h-8 px-2 text-ink-faint">
          <ArrowLeft className="mr-2 h-4 w-4" />
          Back to selection
        </Button>
      </div>
      <PageHeader
        title={comparison.title || "Saved Comparison"}
        subtitle="A detailed breakdown of the selected papers."
      />
      
      <div className="mt-8">
        <ComparePanel
          papers={selectedPapers}
          comparison={comparison}
        />
      </div>
    </div>
  );
}
