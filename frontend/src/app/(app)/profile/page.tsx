"use client";

import Link from "next/link";
import { Mail, Calendar, ShieldCheck, Settings as SettingsIcon } from "lucide-react";
import { PageHeader } from "@/components/shared/page-header";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { useAuth } from "@/contexts/auth-context";

const providerLabel: Record<string, string> = {
  local: "Email & password",
  google: "Google",
  orcid: "ORCID",
};

export default function ProfilePage() {
  const { user } = useAuth();

  if (!user) return null;

  const memberSince = new Date(user.createdAt).toLocaleDateString(undefined, {
    month: "long",
    day: "numeric",
    year: "numeric",
  });

  return (
    <div className="mx-auto max-w-3xl">
      <PageHeader
        title="Profile"
        subtitle="Your account on SAIRA."
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
          {user.avatarUrl && <AvatarImage src={user.avatarUrl} alt={user.name} />}
          <AvatarFallback className="text-xl">{user.avatarInitial}</AvatarFallback>
        </Avatar>
        <div>
          <h2 className="font-display text-xl font-medium text-ink">{user.name}</h2>
          <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-ink-faint">
            <span className="flex items-center gap-1.5">
              <Mail className="h-3.5 w-3.5" /> {user.email}
            </span>
          </div>
        </div>
      </Card>

      <Card className="mt-5 divide-y divide-line-soft p-0">
        <div className="flex items-center justify-between p-5">
          <div className="flex items-center gap-2.5 text-sm text-ink">
            <ShieldCheck className="h-4 w-4 text-ink-faint" />
            Sign-in method
          </div>
          <Badge variant="secondary">{providerLabel[user.provider] ?? user.provider}</Badge>
        </div>
        <div className="flex items-center justify-between p-5">
          <div className="flex items-center gap-2.5 text-sm text-ink">
            <Calendar className="h-4 w-4 text-ink-faint" />
            Member since
          </div>
          <span className="text-sm text-ink-soft">{memberSince}</span>
        </div>
      </Card>
    </div>
  );
}
