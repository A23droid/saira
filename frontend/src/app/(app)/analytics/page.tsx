import { FileStack, NotebookPen, BookMarked, MessageCircle, Flame, Target } from "lucide-react";
import { PageHeader } from "@/components/shared/page-header";
import { StatCard } from "@/components/shared/stat-card";
import { Card } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { MiniBarChart, MiniBreakdownList } from "@/components/shared/mini-charts";
import { analyticsSnapshot } from "@/lib/mock-data";

export default function AnalyticsPage() {
  const a = analyticsSnapshot;
  const goalPct = Math.round((a.weeklyGoal.completed / a.weeklyGoal.target) * 100);

  return (
    <div>
      <PageHeader title="Analytics" subtitle="A look at how your research trail has moved over time." />

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard icon={FileStack} label="Papers saved" value={String(a.totalPapersSaved)} />
        <StatCard icon={NotebookPen} label="Notes written" value={String(a.totalNotes)} accent="brass" />
        <StatCard icon={BookMarked} label="Reviews generated" value={String(a.totalReviews)} />
        <StatCard icon={MessageCircle} label="Questions asked" value={String(a.totalChatQuestions)} accent="brass" />
      </div>

      <div className="mt-5 grid gap-5 lg:grid-cols-3">
        <Card className="p-6 lg:col-span-2">
          <h3 className="mb-1 font-display text-lg font-medium text-ink">Papers read by month</h3>
          <p className="mb-5 text-sm text-ink-soft">Based on reading status changes across your library.</p>
          <MiniBarChart data={a.papersReadByMonth.map((d) => ({ label: d.month, value: d.count }))} />
        </Card>

        <Card className="flex flex-col gap-4 p-6">
          <div className="flex items-center gap-2">
            <Flame className="h-4 w-4 text-brass-600" />
            <h3 className="font-medium text-ink">Reading streak</h3>
          </div>
          <p className="font-display text-4xl text-ink">{a.currentStreakDays}</p>
          <p className="-mt-2 text-sm text-ink-soft">days in a row</p>

          <div className="mt-2 border-t border-line-soft pt-4">
            <div className="mb-2 flex items-center gap-2">
              <Target className="h-4 w-4 text-teal-600" />
              <h3 className="text-sm font-medium text-ink">Weekly goal</h3>
            </div>
            <Progress value={goalPct} />
            <p className="mt-2 text-xs text-ink-faint">
              {a.weeklyGoal.completed} of {a.weeklyGoal.target} papers this week
            </p>
          </div>
        </Card>
      </div>

      <Card className="mt-5 p-6">
        <h3 className="mb-1 font-display text-lg font-medium text-ink">Topics you read most</h3>
        <p className="mb-5 text-sm text-ink-soft">Tag frequency across every paper you've saved.</p>
        <MiniBreakdownList data={a.topicBreakdown.map((d) => ({ label: d.tag, value: d.count }))} accent="brass" />
      </Card>
    </div>
  );
}
