"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useState } from "react";
import {
  Menu,
  X,
  LayoutDashboard,
  Search,
  FolderKanban,
  GitCompareArrows,
  BookMarked,
  Settings,
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
  { href: "/collections", label: "Collections", icon: Layers },
  { href: "/trending", label: "Trending", icon: Flame },
  { href: "/history", label: "History", icon: History },
  { href: "/analytics", label: "Analytics", icon: BarChart3 },
  { href: "/profile", label: "Profile", icon: UserCircle },
  { href: "/settings", label: "Settings", icon: Settings },
];

export function MobileNav() {
  const [open, setOpen] = useState(false);
  const pathname = usePathname();
  const router = useRouter();
  const { user, logout } = useAuth();

  async function handleLogout() {
    setOpen(false);
    await logout();
    router.push("/login");
  }

  return (
    <div className="flex items-center justify-between border-b border-line bg-paper px-4 py-3.5 md:hidden">
      <Link href="/dashboard">
        <Logo />
      </Link>
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex h-9 w-9 items-center justify-center rounded-full hover:bg-paper-dim"
        aria-label="Toggle navigation"
      >
        {open ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
      </button>

      {open && (
        <div className="absolute left-0 right-0 top-[57px] z-40 border-b border-line bg-paper p-3 shadow-lg">
          {user && (
            <div className="mb-2 flex items-center gap-2.5 rounded-xl border border-line-soft bg-paper-dim/50 px-3 py-2.5">
              <Avatar className="h-8 w-8 border border-line">
                {user.avatarUrl && <AvatarImage src={user.avatarUrl} alt={user.name} />}
                <AvatarFallback className="text-xs">{user.avatarInitial}</AvatarFallback>
              </Avatar>
              <div className="min-w-0 flex-1">
                <p className="truncate text-xs font-medium text-ink">{user.name}</p>
                <p className="truncate text-[11px] text-ink-faint">{user.email}</p>
              </div>
            </div>
          )}
          {navItems.map((item) => {
            const active = pathname === item.href || pathname.startsWith(item.href + "/");
            return (
              <Link
                key={item.href}
                href={item.href}
                onClick={() => setOpen(false)}
                className={cn(
                  "flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium",
                  active ? "bg-surface text-ink" : "text-ink-soft"
                )}
              >
                <item.icon className="h-4 w-4" />
                {item.label}
              </Link>
            );
          })}
          <button
            onClick={handleLogout}
            className="flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left text-sm font-medium text-ink-soft"
          >
            <LogOut className="h-4 w-4" />
            Log out
          </button>
        </div>
      )}
    </div>
  );
}
