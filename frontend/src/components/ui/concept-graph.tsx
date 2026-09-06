"use client";

import { useEffect, useRef, useState } from "react";
import { getPaperConcepts, GraphConceptsResponse } from "@/lib/api/papers";
import { Loader2, Lightbulb, Waypoints } from "lucide-react";
import dynamic from "next/dynamic";

const ForceGraph2D = dynamic(() => import("react-force-graph-2d"), {
  ssr: false,
});

interface ConceptGraphProps {
  paperId: string;
  paperTitle: string;
}

export function ConceptGraph({ paperId, paperTitle }: ConceptGraphProps) {
  const [loading, setLoading] = useState(true);
  const [data, setData] = useState<GraphConceptsResponse | null>(null);
  const [error, setError] = useState(false);
  const [dimensions, setDimensions] = useState({ width: 0, height: 0 });
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let active = true;
    getPaperConcepts(paperId)
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

  useEffect(() => {
    if (containerRef.current) {
      const { width } = containerRef.current.getBoundingClientRect();
      setDimensions({ width, height: 500 });
    }

    const handleResize = () => {
      if (containerRef.current) {
        setDimensions({
          width: containerRef.current.getBoundingClientRect().width,
          height: 500,
        });
      }
    };

    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, [data]);

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center py-20 text-ink-faint">
        <Loader2 className="h-8 w-8 animate-spin mb-4" />
        <p>Extracting concepts...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center py-20 text-red-500">
        <Lightbulb className="h-8 w-8 mb-4 opacity-50" />
        <p>Failed to load concepts.</p>
      </div>
    );
  }

  if (!data || data.nodes.length === 0 || (data.nodes.length === 1 && data.nodes[0].id === paperId)) {
    return (
      <div className="flex flex-col items-center justify-center py-20 text-ink-faint bg-surface border border-line rounded-xl">
        <Lightbulb className="h-10 w-10 mb-4 opacity-30" />
        <p className="text-sm font-medium text-ink">No concepts found</p>
        <p className="text-xs max-w-sm text-center mt-2">
          Concepts might be extracting in the background. Try refreshing in a few moments.
        </p>
      </div>
    );
  }

  // Format data for react-force-graph
  const graphData = {
    nodes: data.nodes.map(n => ({ ...n, val: n.type === "Paper" ? 2 : 1 })),
    links: data.edges.map(e => ({ source: e.source, target: e.target, name: e.label }))
  };

  return (
    <div className="flex flex-col rounded-xl border border-line bg-surface shadow-sm overflow-hidden" ref={containerRef}>
      <div className="flex items-center gap-2 p-4 border-b border-line bg-surface">
        <Waypoints className="h-4 w-4 text-brass-600" />
        <h3 className="text-sm font-medium text-ink">Concept map</h3>
      </div>
      
      {dimensions.width > 0 && (
        <div className="bg-surface relative flex items-center justify-center w-full min-h-[500px]">
          <ForceGraph2D
            width={dimensions.width}
            height={dimensions.height}
            graphData={graphData}
            nodeLabel="label"
            nodeColor={(node: any) => {
              if (node.type === "Paper") return "#0f766e"; // teal-700
              if (node.type === "Concept") return "#d97706"; // amber-600
              if (node.type === "Method") return "#2563eb"; // blue-600
              if (node.type === "Dataset") return "#16a34a"; // green-600
              return "#475569"; // slate-600
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
              console.log("Clicked:", node);
            }}
          />
        </div>
      )}
    </div>
  );
}
