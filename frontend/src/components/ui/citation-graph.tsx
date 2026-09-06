"use client";

import { useEffect, useState } from "react";
import { getPaperCitations, CitationNode } from "@/lib/api/papers";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Loader2, ExternalLink, Network, FileText, Ban } from "lucide-react";
import { motion } from "framer-motion";

interface CitationGraphProps {
  paperId: string;
  paperTitle: string;
}

export function CitationGraph({ paperId, paperTitle }: CitationGraphProps) {
  const [loading, setLoading] = useState(true);
  const [data, setData] = useState<{ citations: CitationNode[]; references: CitationNode[] } | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    let active = true;
    getPaperCitations(paperId)
      .then((res) => {
        if (active) {
          setData(res);
          setLoading(false);
        }
      })
      .catch((err) => {
        console.error(err);
        if (active) {
          setError(true);
          setLoading(false);
        }
      });
    return () => {
      active = false;
    };
  }, [paperId]);

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center py-20 text-ink-faint">
        <Loader2 className="h-8 w-8 animate-spin mb-4" />
        <p>Loading citation graph...</p>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="flex flex-col items-center justify-center py-20 text-red-500">
        <Network className="h-8 w-8 mb-4 opacity-50" />
        <p>Failed to load citation graph.</p>
      </div>
    );
  }

  if (data.citations.length === 0 && data.references.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-20 text-ink-faint bg-surface border border-line rounded-xl">
        <Network className="h-10 w-10 mb-4 opacity-30" />
        <p className="text-sm font-medium text-ink">Graph data is currently empty</p>
        <p className="text-xs max-w-sm text-center mt-2">
          Citation data might be syncing in the background, or Semantic Scholar has no records for this paper. Try refreshing in a few moments.
        </p>
      </div>
    );
  }

  const renderNode = (node: CitationNode, direction: "left" | "right") => {
    const isAccessible = node.has_pdf !== false;
    
    return (
      <motion.div
        initial={{ opacity: 0, x: direction === "left" ? -20 : 20 }}
        animate={{ opacity: 1, x: 0 }}
        key={node.id}
      >
        <Card className={`p-3 text-sm relative group overflow-hidden ${isAccessible ? 'hover:border-teal-400 hover:shadow-md cursor-pointer bg-surface' : 'bg-surface/30 opacity-70 border-dashed cursor-not-allowed'}`}
          onClick={() => {
            if (isAccessible && node.id) {
              window.open(`/papers/${node.id}`, '_blank');
            }
          }}
        >
          {!isAccessible && (
            <div className="absolute top-2 right-2 flex items-center justify-center bg-line/50 p-1 rounded-full" title="PDF not available">
              <Ban className="h-3 w-3 text-ink-faint" />
            </div>
          )}
          <h4 className={`font-medium line-clamp-2 leading-tight mb-2 pr-5 ${!isAccessible ? 'text-ink-soft' : 'text-ink'}`}>
            {node.title}
          </h4>
          <div className="flex items-center gap-2 text-xs text-ink-faint">
            {node.year && <Badge variant="secondary" className="text-[10px] px-1.5 py-0 bg-paper-dim">{node.year}</Badge>}
            {isAccessible && (
              <span className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity ml-auto text-teal-600">
                <ExternalLink className="h-3 w-3" /> View
              </span>
            )}
          </div>
        </Card>
      </motion.div>
    );
  };

  return (
    <div className="w-full flex flex-col items-center bg-paper-dim/10 rounded-xl p-4 sm:p-8 min-h-[500px]">
      <div className="mb-8 text-center">
        <h3 className="text-lg font-medium flex items-center gap-2 justify-center">
          <Network className="h-5 w-5 text-teal-600" />
          Research Lineage
        </h3>
        <p className="text-xs text-ink-faint mt-1">Citations and references fetched via Semantic Scholar</p>
      </div>

      <div className="w-full grid grid-cols-1 md:grid-cols-3 gap-6 md:gap-4 relative">
        
        {/* References Column (Left) */}
        <div className="flex flex-col gap-4">
          <div className="text-center font-medium text-xs uppercase tracking-wider text-ink-soft mb-2">
            References ({data.references.length})
            <p className="text-[10px] text-ink-faint normal-case tracking-normal mt-0.5">Papers this built upon</p>
          </div>
          <ScrollArea className="h-[400px] w-full pr-4">
            <div className="flex flex-col gap-3 pb-4">
              {data.references.map(r => renderNode(r, "left"))}
              {data.references.length === 0 && (
                <div className="text-center p-4 border border-dashed border-line rounded-lg text-xs text-ink-faint">
                  No references found
                </div>
              )}
            </div>
          </ScrollArea>
        </div>

        {/* Current Paper (Center) */}
        <div className="flex items-center justify-center relative hidden md:flex">
          {/* Connecting lines - visual only */}
          <div className="absolute left-0 right-1/2 top-1/2 h-[2px] bg-gradient-to-r from-transparent via-teal-200 to-teal-400 -z-10" />
          <div className="absolute left-1/2 right-0 top-1/2 h-[2px] bg-gradient-to-r from-teal-400 via-teal-200 to-transparent -z-10" />
          
          <motion.div 
            initial={{ scale: 0.9, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            className="w-full max-w-[250px] bg-teal-50 border-2 border-teal-500 rounded-xl p-4 shadow-lg text-center z-10"
          >
            <div className="bg-teal-500 w-8 h-8 rounded-full flex items-center justify-center mx-auto mb-3 shadow-inner">
              <FileText className="h-4 w-4 text-white" />
            </div>
            <h3 className="font-semibold text-teal-900 text-sm line-clamp-3 mb-2">{paperTitle}</h3>
            <Badge className="bg-teal-100 text-teal-800 hover:bg-teal-100 border-none">Current Paper</Badge>
          </motion.div>
        </div>

        {/* Citations Column (Right) */}
        <div className="flex flex-col gap-4">
          <div className="text-center font-medium text-xs uppercase tracking-wider text-ink-soft mb-2">
            Citations ({data.citations.length})
            <p className="text-[10px] text-ink-faint normal-case tracking-normal mt-0.5">Papers building on this</p>
          </div>
          <ScrollArea className="h-[400px] w-full pr-4">
            <div className="flex flex-col gap-3 pb-4">
              {data.citations.map(c => renderNode(c, "right"))}
              {data.citations.length === 0 && (
                <div className="text-center p-4 border border-dashed border-line rounded-lg text-xs text-ink-faint">
                  No citations found
                </div>
              )}
            </div>
          </ScrollArea>
        </div>

      </div>
    </div>
  );
}
