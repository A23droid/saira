"use client";

import { motion } from "framer-motion";

export function MiniBarChart({
  data,
  accent = "teal",
}: {
  data: { label: string; value: number }[];
  accent?: "teal" | "brass";
}) {
  const max = Math.max(...data.map((d) => d.value), 1);
  const fill = accent === "teal" ? "var(--teal-600)" : "var(--brass-600)";

  return (
    <div className="flex h-40 items-end gap-3">
      {data.map((d, i) => (
        <div key={d.label} className="flex flex-1 flex-col items-center gap-2">
          <div className="flex h-32 w-full items-end overflow-hidden rounded-lg bg-paper-dim/50">
            <motion.div
              className="w-full rounded-lg"
              style={{ background: fill }}
              initial={{ height: 0 }}
              animate={{ height: `${(d.value / max) * 100}%` }}
              transition={{ duration: 0.6, delay: i * 0.05, ease: "easeOut" }}
            />
          </div>
          <span className="text-xs font-medium text-ink-faint">{d.label}</span>
        </div>
      ))}
    </div>
  );
}

export function MiniBreakdownList({
  data,
  accent = "teal",
}: {
  data: { label: string; value: number }[];
  accent?: "teal" | "brass";
}) {
  const max = Math.max(...data.map((d) => d.value), 1);
  const fill = accent === "teal" ? "var(--teal-600)" : "var(--brass-600)";

  return (
    <div className="flex flex-col gap-3">
      {data.map((d) => (
        <div key={d.label}>
          <div className="mb-1 flex items-center justify-between text-xs">
            <span className="font-medium text-ink">{d.label}</span>
            <span className="text-ink-faint">{d.value}</span>
          </div>
          <div className="h-2 w-full overflow-hidden rounded-full bg-paper-dim">
            <div
              className="h-full rounded-full"
              style={{ width: `${(d.value / max) * 100}%`, background: fill }}
            />
          </div>
        </div>
      ))}
    </div>
  );
}
