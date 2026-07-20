import { cn } from "@/lib/utils";

/** A thin dotted "trail" line — the recurring wayfinding motif across SAIRA. */
export function TrailDivider({ className }: { className?: string }) {
  return <div className={cn("trail-line w-full", className)} aria-hidden />;
}

interface Milestone {
  label: string;
  done: boolean;
}

/** Horizontal trail of milestones, echoing a route marked with waypoints. */
export function MilestoneTrail({ milestones }: { milestones: Milestone[] }) {
  return (
    <div className="flex items-center">
      {milestones.map((m, i) => (
        <div key={m.label} className="flex flex-1 items-center last:flex-none">
          <div className="flex flex-col items-center gap-2">
            <div
              className={cn(
                "flex h-3.5 w-3.5 items-center justify-center rounded-full border-2",
                m.done ? "border-teal-600 bg-teal-600" : "border-line bg-surface"
              )}
            />
            <span
              className={cn(
                "whitespace-nowrap text-xs font-medium",
                m.done ? "text-ink" : "text-ink-faint"
              )}
            >
              {m.label}
            </span>
          </div>
          {i < milestones.length - 1 && (
            <div
              className={cn(
                "trail-line mx-2 mb-5 flex-1",
                m.done && milestones[i + 1].done ? "opacity-100" : "opacity-60"
              )}
            />
          )}
        </div>
      ))}
    </div>
  );
}
