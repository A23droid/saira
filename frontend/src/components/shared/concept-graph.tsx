import { ConceptGraphData } from "@/lib/api/papers";
import { Card } from "@/components/ui/card";
import { Waypoints, ArrowRight } from "lucide-react";
import { Badge } from "@/components/ui/badge";

export function ConceptGraph({ data }: { data: ConceptGraphData }) {
  if (!data || data.nodes.length === 0) {
    return (
      <div className="flex h-48 w-full flex-col items-center justify-center rounded-xl border border-dashed border-line bg-surface/50 text-center px-4">
        <Waypoints className="mb-2 h-6 w-6 text-brass-400" />
        <h3 className="text-sm font-medium text-ink">Concept graph</h3>
        <p className="mt-1 text-xs text-ink-faint">No concepts extracted for this paper yet.</p>
      </div>
    );
  }

  return (
    <div className="flex flex-col rounded-xl border border-line bg-surface p-6 shadow-sm overflow-x-auto">
      <div className="mb-4 flex items-center gap-2">
        <Waypoints className="h-4 w-4 text-brass-600" />
        <h3 className="text-sm font-medium text-ink">Concept graph</h3>
      </div>
      
      <div className="flex flex-col gap-4 p-2 min-w-[300px]">
        {data.edges.map((edge, i) => {
          const sourceNode = data.nodes.find(n => n.id === edge.source);
          const targetNode = data.nodes.find(n => n.id === edge.target);
          if (!sourceNode || !targetNode) return null;
          
          return (
            <div key={i} className="flex items-center gap-3">
              <Card className="p-2 border-brass-200 bg-brass-50/50 flex-1 text-center truncate">
                <Badge variant="outline" className="text-[9px] mb-1 opacity-70 bg-transparent border-brass-300 text-brass-800">{sourceNode.type}</Badge>
                <p className="text-xs font-medium text-ink truncate">{sourceNode.label}</p>
              </Card>
              
              <div className="flex flex-col items-center flex-[0.5]">
                <p className="text-[10px] text-brass-600 italic whitespace-nowrap mb-0.5">{edge.label}</p>
                <ArrowRight className="h-4 w-4 text-brass-400" />
              </div>
              
              <Card className="p-2 border-brass-200 bg-brass-50/50 flex-1 text-center truncate">
                <Badge variant="outline" className="text-[9px] mb-1 opacity-70 bg-transparent border-brass-300 text-brass-800">{targetNode.type}</Badge>
                <p className="text-xs font-medium text-ink truncate">{targetNode.label}</p>
              </Card>
            </div>
          );
        })}
      </div>
    </div>
  );
}
