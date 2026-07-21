import { BookOpenCheck } from "lucide-react";
import { Card } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { Paper } from "@/lib/types";

const progressByStatus: Record<Paper["readingStatus"], number> = {
  unread: 0,
  reading: 55,
  read: 100,
};

const labelByStatus: Record<Paper["readingStatus"], string> = {
  unread: "Not started",
  reading: "In progress",
  read: "Finished",
};

export function ReadingProgressCard({ status }: { status: Paper["readingStatus"] }) {
  return (
    <Card className="flex flex-col gap-3 p-5">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <BookOpenCheck className="h-4 w-4 text-teal-600" />
          <h3 className="text-sm font-medium text-ink">Reading progress</h3>
        </div>
        <span className="text-xs font-medium text-ink-faint">{labelByStatus[status]}</span>
      </div>
      <Progress value={progressByStatus[status]} />
      <p className="text-xs text-ink-faint">
        Estimated from time spent on the PDF viewer and Ask AI activity for this paper.
      </p>
    </Card>
  );
}
