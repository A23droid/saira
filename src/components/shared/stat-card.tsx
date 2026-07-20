import { LucideIcon } from "lucide-react";
import { Card } from "@/components/ui/card";
import { cn } from "@/lib/utils";

export function StatCard({
  icon: Icon,
  label,
  value,
  hint,
  accent = "teal",
}: {
  icon: LucideIcon;
  label: string;
  value: string;
  hint?: string;
  accent?: "teal" | "brass";
}) {
  return (
    <Card className="flex items-center gap-4 p-5">
      <div
        className={cn(
          "flex h-11 w-11 shrink-0 items-center justify-center rounded-full",
          accent === "teal" ? "bg-teal-50 text-teal-600" : "bg-brass-100 text-brass-600"
        )}
      >
        <Icon className="h-5 w-5" />
      </div>
      <div>
        <p className="font-display text-2xl font-medium leading-none text-ink">{value}</p>
        <p className="mt-1 text-sm text-ink-soft">{label}</p>
        {hint && <p className="mt-0.5 text-xs text-ink-faint">{hint}</p>}
      </div>
    </Card>
  );
}
