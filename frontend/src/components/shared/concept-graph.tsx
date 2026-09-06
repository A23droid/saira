"use client";

import { useEffect, useRef, useState } from "react";
// The project-scoped concept graph type lives in the projects API module;
// importing it from papers.ts silently resolved to nothing and left this
// component's props untyped.
import { ConceptGraphData, ConceptGraphNode, ConceptGraphEdge } from "@/lib/api/projects";
import { Waypoints } from "lucide-react";
import dynamic from "next/dynamic";

// Force graph uses canvas and window, must be loaded dynamically on client
const ForceGraph2D = dynamic(() => import("react-force-graph-2d"), {
  ssr: false,
});

export function ConceptGraph({ data }: { data: ConceptGraphData }) {
  const [dimensions, setDimensions] = useState({ width: 0, height: 0 });
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (containerRef.current) {
      const { width } = containerRef.current.getBoundingClientRect();
      setDimensions({ width, height: 400 }); // Fixed height for graph
    }

    const handleResize = () => {
      if (containerRef.current) {
        setDimensions({
          width: containerRef.current.getBoundingClientRect().width,
          height: 400,
        });
      }
    };

    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, [data]);

  if (!data || data.nodes.length === 0) {
    return (
      <div className="flex h-48 w-full flex-col items-center justify-center rounded-xl border border-dashed border-line bg-surface/50 text-center px-4">
        <Waypoints className="mb-2 h-6 w-6 text-brass-400" />
        <h3 className="text-sm font-medium text-ink">Concept graph</h3>
        <p className="mt-1 text-xs text-ink-faint">No concepts extracted for this paper yet.</p>
      </div>
    );
  }

  // Format data for react-force-graph
  const graphData = {
    nodes: data.nodes.map((n: ConceptGraphNode) => ({ ...n, val: n.type === "paper" ? 2 : 1 })),
    links: data.edges.map((e: ConceptGraphEdge) => ({ source: e.source, target: e.target, name: e.label }))
  };

  return (
    <div className="flex flex-col rounded-xl border border-line bg-surface shadow-sm overflow-hidden" ref={containerRef}>
      <div className="flex items-center gap-2 p-4 border-b border-line bg-surface">
        <Waypoints className="h-4 w-4 text-brass-600" />
        <h3 className="text-sm font-medium text-ink">Concept graph</h3>
      </div>
      
      {dimensions.width > 0 && (
        <div className="bg-surface relative">
          <ForceGraph2D
            width={dimensions.width}
            height={dimensions.height}
            graphData={graphData}
            nodeLabel="label"
            nodeColor={(node: any) => {
              // The per-paper API returns "Paper"/"Concept" while the project
              // API returns "paper"/"concept"; comparing case-sensitively meant
              // every project-graph node fell through to the default colour.
              switch (String(node.type ?? "").toLowerCase()) {
                case "paper": return "#0f766e";   // teal-700
                case "concept": return "#d97706"; // amber-600
                case "method": return "#2563eb";  // blue-600
                case "dataset": return "#16a34a"; // green-600
                default: return "#475569";        // slate-600
              }
            }}
            nodeRelSize={6}
            linkColor={() => "#cbd5e1"} // slate-300
            linkDirectionalArrowLength={3.5}
            linkDirectionalArrowRelPos={1}
            linkCurvature={0.25}
            linkLabel="name"
            d3AlphaDecay={0.05}
            d3VelocityDecay={0.4}
            onNodeClick={(node: any) => {
              // Can add specific logic here later
              console.log("Clicked:", node);
            }}
          />
        </div>
      )}
    </div>
  );
}
