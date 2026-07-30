"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  LayoutDashboard,
  Search,
  FolderKanban,
  GitCompareArrows,
  BookMarked,
  Settings,
  Compass,
  Layers,
  Flame,
  History,
  BarChart3,
  UserCircle,
  LogOut,
} from "lucide-react";
import { Logo } from "@/components/shared/logo";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { useAuth } from "@/contexts/auth-context";
import { cn } from "@/lib/utils";

const navItems = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { href: "/search", label: "Search papers", icon: Search },
  { href: "/projects", label: "Projects", icon: FolderKanban },
  { href: "/compare", label: "Compare", icon: GitCompareArrows },
  { href: "/review", label: "Literature review", icon: BookMarked },
];

const exploreItems = [
  { href: "/collections", label: "Collections", icon: Layers },
  { href: "/trending", label: "Trending", icon: Flame },
  { href: "/history", label: "History", icon: History },
  { href: "/analytics", label: "Analytics", icon: BarChart3 },
];

export function Sidebar() {
  const pathname = usePathname();
  const router = useRouter();
  const { user, logout } = useAuth();

  async function handleLogout() {
    await logout();
    router.push("/login");
  }

  return (
    <aside className="hidden w-64 shrink-0 flex-col border-r border-line bg-paper-dim/50 px-4 py-6 md:flex">
      <Link href="/dashboard" className="px-2">
        <Logo />
      </Link>

      <nav className="mt-9 flex flex-1 flex-col gap-1">
        <p className="px-3 pb-2 text-xs font-medium uppercase tracking-wide text-ink-faint">
          Navigate
        </p>
        {navItems.map((item) => {
          const active = pathname === item.href || pathname.startsWith(item.href + "/");
          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium transition-colors",
                active
                  ? "bg-surface text-ink shadow-sm"
                  : "text-ink-soft hover:bg-surface/70 hover:text-ink"
              )}
            >
              <item.icon className={cn("h-4 w-4", active ? "text-teal-600" : "text-ink-faint")} />
              {item.label}
            </Link>
          );
        })}

        <p className="mt-5 px-3 pb-2 text-xs font-medium uppercase tracking-wide text-ink-faint">
          Explore
        </p>
        {exploreItems.map((item) => {
          const active = pathname === item.href || pathname.startsWith(item.href + "/");
          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium transition-colors",
                active
                  ? "bg-surface text-ink shadow-sm"
                  : "text-ink-soft hover:bg-surface/70 hover:text-ink"
              )}
            >
              <item.icon className={cn("h-4 w-4", active ? "text-teal-600" : "text-ink-faint")} />
              {item.label}
            </Link>
          );
        })}
      </nav>

      {user && (
        <div className="mb-2 flex items-center gap-2.5 rounded-xl border border-line-soft bg-surface/60 px-3 py-2.5">
          <Avatar className="h-8 w-8 border border-line">
            {user.avatarUrl && <AvatarImage src={user.avatarUrl} alt={user.name} />}
            <AvatarFallback className="text-xs">{user.avatarInitial}</AvatarFallback>
          </Avatar>
          <div className="min-w-0 flex-1">
            <p className="truncate text-xs font-medium text-ink">{user.name}</p>
            <p className="truncate text-[11px] text-ink-faint">{user.email}</p>
          </div>
          <button
            onClick={handleLogout}
            title="Log out"
            aria-label="Log out"
            className="shrink-0 rounded-full p-1.5 text-ink-faint transition-colors hover:bg-paper-dim hover:text-ink"
          >
            <LogOut className="h-3.5 w-3.5" />
          </button>
        </div>
      )}

      <Link
        href="/profile"
        className={cn(
          "flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium transition-colors",
          pathname === "/profile"
            ? "bg-surface text-ink shadow-sm"
            : "text-ink-soft hover:bg-surface/70 hover:text-ink"
        )}
      >
        <UserCircle className={cn("h-4 w-4", pathname === "/profile" ? "text-teal-600" : "text-ink-faint")} />
        Profile
      </Link>

      <Link
        href="/settings"
        className={cn(
          "flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium transition-colors",
          pathname === "/settings"
            ? "bg-surface text-ink shadow-sm"
            : "text-ink-soft hover:bg-surface/70 hover:text-ink"
        )}
      >
        <Settings className={cn("h-4 w-4", pathname === "/settings" ? "text-teal-600" : "text-ink-faint")} />
        Settings
      </Link>

      <div className="mt-5 flex items-start gap-2.5 rounded-xl border border-line-soft bg-surface/60 px-3 py-3">
        <Compass className="mt-0.5 h-4 w-4 shrink-0 text-brass-600" />
        <p className="text-xs leading-relaxed text-ink-soft">
          Every project keeps its own trail — papers, notes, and comparisons in one route.
        </p>
      </div>
    </aside>
  );
}
