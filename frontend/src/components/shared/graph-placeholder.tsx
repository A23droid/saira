import { LucideIcon } from "lucide-react";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

/**
 * A decorative, static node-graph illustration used to preview graph-based
 * features that aren't wired to real data yet (citation graph, concept graph).
 * Kept intentionally abstract rather than a literal chart, so it reads as a
 * preview rather than a broken visualization.
 */
function NodeGraphPreview({ accent = "teal" }: { accent?: "teal" | "brass" }) {
  const stroke = accent === "teal" ? "#12796b" : "#a8792f";
  const nodes = [
    { x: 60, y: 70 },
    { x: 150, y: 30 },
    { x: 230, y: 80 },
    { x: 130, y: 120 },
    { x: 210, y: 150 },
    { x: 40, y: 140 },
  ];
  const edges: [number, number][] = [
    [0, 1],
    [1, 2],
    [0, 3],
    [3, 4],
    [2, 4],
    [3, 5],
  ];

  return (
    <svg viewBox="0 0 270 180" className="h-full w-full" xmlns="http://www.w3.org/2000/svg">
      {edges.map(([a, b], i) => (
        <line
          key={i}
          x1={nodes[a].x}
          y1={nodes[a].y}
          x2={nodes[b].x}
          y2={nodes[b].y}
          stroke="#e7e0d2"
          strokeWidth="1.5"
        />
      ))}
      {nodes.map((n, i) => (
        <circle
          key={i}
          cx={n.x}
          cy={n.y}
          r={i === 0 ? 9 : 6}
          fill={i === 0 ? stroke : "#ffffff"}
          stroke={stroke}
          strokeWidth="1.6"
        />
      ))}
    </svg>
  );
}

export function GraphPlaceholder({
  icon: Icon,
  title,
  description,
  accent = "teal",
  className,
}: {
  icon: LucideIcon;
  title: string;
  description: string;
  accent?: "teal" | "brass";
  className?: string;
}) {
  return (
    <Card className={cn("flex flex-col gap-4 p-6", className)}>
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-2.5">
          <span
            className={cn(
              "flex h-9 w-9 items-center justify-center rounded-full",
              accent === "teal" ? "bg-teal-50 text-teal-600" : "bg-brass-100 text-brass-600"
            )}
          >
            <Icon className="h-4 w-4" />
          </span>
          <h3 className="font-display text-lg font-medium text-ink">{title}</h3>
        </div>
        <Badge variant="outline">Coming soon</Badge>
      </div>
      <p className="text-sm leading-relaxed text-ink-soft">{description}</p>
      <div className="flex h-40 items-center justify-center rounded-xl border border-dashed border-line bg-paper-dim/30 p-4">
        <NodeGraphPreview accent={accent} />
      </div>
    </Card>
  );
}
