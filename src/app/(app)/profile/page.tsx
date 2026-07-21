import Link from "next/link";
import { Mail, Building2, Award, Settings as SettingsIcon } from "lucide-react";
import { PageHeader } from "@/components/shared/page-header";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { StatCard } from "@/components/shared/stat-card";
import { HistoryTimeline } from "@/components/shared/history-timeline";
import { FileStack, NotebookPen, BookMarked } from "lucide-react";
import { currentUser, analyticsSnapshot, badges, historyEvents } from "@/lib/mock-data";

export default function ProfilePage() {
  const recentActivity = [...historyEvents]
    .sort((a, b) => (a.timestamp < b.timestamp ? 1 : -1))
    .slice(0, 4);

  return (
    <div className="mx-auto max-w-3xl">
      <PageHeader
        title="Profile"
        subtitle="Your research identity across SAIRA."
        actions={
          <Link href="/settings">
            <Button variant="outline" className="gap-1.5">
              <SettingsIcon className="h-3.5 w-3.5" />
              Edit in settings
            </Button>
          </Link>
        }
      />

      <Card className="flex flex-col items-start gap-5 p-7 sm:flex-row sm:items-center">
        <Avatar className="h-16 w-16 border border-line">
          <AvatarFallback className="text-xl">{currentUser.avatarInitial}</AvatarFallback>
        </Avatar>
        <div>
          <h2 className="font-display text-xl font-medium text-ink">{currentUser.name}</h2>
          <p className="text-sm text-ink-soft">{currentUser.role}</p>
          <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-ink-faint">
            <span className="flex items-center gap-1.5">
              <Mail className="h-3.5 w-3.5" /> {currentUser.email}
            </span>
            <span className="flex items-center gap-1.5">
              <Building2 className="h-3.5 w-3.5" /> {currentUser.institution}
            </span>
          </div>
        </div>
      </Card>

      <div className="mt-5 grid gap-4 sm:grid-cols-3">
        <StatCard icon={FileStack} label="Papers saved" value={String(analyticsSnapshot.totalPapersSaved)} />
        <StatCard icon={NotebookPen} label="Notes written" value={String(analyticsSnapshot.totalNotes)} accent="brass" />
        <StatCard icon={BookMarked} label="Reviews drafted" value={String(analyticsSnapshot.totalReviews)} />
      </div>

      <Card className="mt-5 p-6">
        <div className="mb-4 flex items-center gap-2">
          <Award className="h-4 w-4 text-brass-600" />
          <h3 className="font-medium text-ink">Badges</h3>
        </div>
        <div className="flex flex-wrap gap-2">
          {badges.map((b) => (
            <Badge key={b.label} variant="brass" title={b.description}>
              {b.label}
            </Badge>
          ))}
        </div>
      </Card>

      <Card className="mt-5 p-6">
        <div className="mb-4 flex items-center justify-between">
          <h3 className="font-medium text-ink">Recent activity</h3>
          <Link href="/history" className="text-sm font-medium text-teal-700 hover:underline">
            View all
          </Link>
        </div>
        <HistoryTimeline events={recentActivity} />
      </Card>
    </div>
  );
}
