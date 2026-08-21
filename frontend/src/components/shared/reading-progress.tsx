import { BookOpenCheck } from "lucide-react";
import { Card } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";

interface ReadingProgressCardProps {
  percent: number;
  status: string;
  onUpdatePercent: (p: number) => void;
  onUpdateStatus: (s: string) => void;
  disabled?: boolean;
}

const statusOptions = [
  { value: "unread", label: "Not started" },
  { value: "reading", label: "In progress" },
  { value: "read", label: "Finished" },
];

export function ReadingProgressCard({ percent, status, onUpdatePercent, onUpdateStatus, disabled }: ReadingProgressCardProps) {
  return (
    <Card className="flex flex-col gap-3 p-5">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <BookOpenCheck className="h-4 w-4 text-teal-600" />
          <h3 className="text-sm font-medium text-ink">Reading progress</h3>
        </div>
        <select 
          className="text-xs font-medium text-ink bg-transparent border-none outline-none cursor-pointer"
          value={status || "unread"}
          onChange={(e) => onUpdateStatus(e.target.value)}
          disabled={disabled}
        >
          {statusOptions.map(opt => (
            <option key={opt.value} value={opt.value}>{opt.label}</option>
          ))}
        </select>
      </div>
      <div className="flex items-center gap-2">
        <Progress value={percent} className="flex-1" />
        <span className="text-xs font-mono text-ink-faint w-8 text-right">{percent}%</span>
      </div>
      
      {!disabled && (
        <div className="flex gap-2 justify-between mt-1">
          {[0, 25, 50, 75, 100].map(p => (
            <button 
              key={p} 
              onClick={() => onUpdatePercent(p)}
              className="text-[10px] text-ink-soft hover:text-teal-700 bg-surface border border-line rounded px-1.5 py-0.5"
            >
              {p}%
            </button>
          ))}
        </div>
      )}
      
      <p className="text-xs text-ink-faint mt-1">
        Manually track your progress since the PDF viewer MVP is simplified.
      </p>
    </Card>
  );
}
