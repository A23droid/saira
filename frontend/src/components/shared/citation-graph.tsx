import { CitationGraphData } from "@/lib/api/projects";
import { Card } from "@/components/ui/card";
import { ArrowRight, Share2 } from "lucide-react";
import Link from "next/link";

export function CitationGraph({ data }: { data: CitationGraphData }) {
  if (!data || data.nodes.length === 0) {
    return (
      <div className="flex h-48 w-full flex-col items-center justify-center rounded-xl border border-dashed border-line bg-surface/50 text-center px-4">
        <Share2 className="mb-2 h-6 w-6 text-ink-faint" />
        <h3 className="text-sm font-medium text-ink">Citation graph</h3>
        <p className="mt-1 text-xs text-ink-faint">No citation data available for this paper.</p>
      </div>
    );
  }

  const targetNode = data.nodes.find(n => n.group === 1);
  const citedByTarget = data.nodes.filter(n => n.group === 2);
  const citingTarget = data.nodes.filter(n => n.group === 3);

  return (
    <div className="flex flex-col rounded-xl border border-line bg-surface p-6 shadow-sm overflow-x-auto">
      <div className="mb-4 flex items-center gap-2">
        <Share2 className="h-4 w-4 text-teal-600" />
        <h3 className="text-sm font-medium text-ink">Citation graph</h3>
      </div>
      
      <div className="flex items-center min-w-[600px] gap-6 p-4">
        {/* Left Column: Papers cited by target */}
        <div className="flex flex-1 flex-col gap-3">
          <h4 className="text-xs font-semibold uppercase tracking-wider text-ink-faint text-center mb-2">References (Cited By)</h4>
          {citedByTarget.length === 0 && (
             <p className="text-xs text-ink-faint text-center">No references found.</p>
          )}
          {citedByTarget.map(node => (
            <Link key={node.id} href={`/papers/${node.id}`}>
              <Card className="p-3 hover:border-teal-500 hover:bg-teal-50/40 transition-colors">
                <p className="text-xs font-medium text-ink line-clamp-2">{node.label}</p>
                {node.year && <p className="text-[10px] text-ink-faint mt-1">{node.year}</p>}
              </Card>
            </Link>
          ))}
        </div>
        
        {/* Arrows */}
        <div className="flex flex-col items-center text-teal-500">
          <ArrowRight className="h-5 w-5" />
        </div>

        {/* Center Column: Target */}
        <div className="flex flex-[1.2] flex-col gap-3 justify-center">
          <h4 className="text-xs font-semibold uppercase tracking-wider text-ink-faint text-center mb-2">Target Paper</h4>
          {targetNode && (
            <Card className="p-4 border-2 border-teal-500 bg-teal-50/20 shadow-md">
              <p className="text-sm font-medium text-teal-900 line-clamp-3">{targetNode.label}</p>
              {targetNode.year && <p className="text-xs text-teal-700 mt-2 font-medium">{targetNode.year}</p>}
            </Card>
          )}
        </div>
        
        {/* Arrows */}
        <div className="flex flex-col items-center text-teal-500">
          <ArrowRight className="h-5 w-5" />
        </div>
        
        {/* Right Column: Papers citing target */}
        <div className="flex flex-1 flex-col gap-3">
          <h4 className="text-xs font-semibold uppercase tracking-wider text-ink-faint text-center mb-2">Citations (Citing)</h4>
          {citingTarget.length === 0 && (
             <p className="text-xs text-ink-faint text-center">No citations found.</p>
          )}
          {citingTarget.map(node => (
            <Link key={node.id} href={`/papers/${node.id}`}>
              <Card className="p-3 hover:border-teal-500 hover:bg-teal-50/40 transition-colors">
                <p className="text-xs font-medium text-ink line-clamp-2">{node.label}</p>
                {node.year && <p className="text-[10px] text-ink-faint mt-1">{node.year}</p>}
              </Card>
            </Link>
          ))}
        </div>
      </div>
    </div>
  );
}
