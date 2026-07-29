"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  BarChart2,
  ClipboardList,
  Cpu,
  FolderGit2,
  LogOut,
  Plus,
  Settings,
  Terminal,
} from "lucide-react";
import type { CurrentUserResponse } from "@/types/api";

const navItems = [
  { href: "/tasks", label: "Tasks", icon: ClipboardList, color: "text-blue-400" },
  { href: "/repositories", label: "Repositories", icon: FolderGit2, color: "text-violet-400" },
  { href: "/evaluations", label: "Evaluations", icon: BarChart2, color: "text-emerald-400" },
  { href: "/system-status", label: "System", icon: Cpu, color: "text-amber-400" },
  { href: "/settings", label: "Settings", icon: Settings, color: "text-zinc-400" },
];

interface SidebarProps {
  user: CurrentUserResponse;
  onOpenCreateTask: () => void;
  onLogout: () => void;
  isLoggingOut: boolean;
}

export function Sidebar({
  user,
  onOpenCreateTask,
  onLogout,
  isLoggingOut,
}: SidebarProps) {
  const pathname = usePathname();
  const displayName = user.github_name || user.github_login;

  return (
    <nav
      aria-label="Sidebar"
      className="fixed left-0 top-0 z-50 flex h-full w-16 shrink-0 flex-col border-r border-[#27272A] bg-[#18181B] transition-all lg:w-64"
    >
      <div className="flex h-16 shrink-0 items-center border-b border-[#27272A] px-4">
        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-blue-600 shadow-[0_0_15px_rgba(37,99,235,0.4)]">
          <Terminal className="h-4 w-4 text-white" />
        </div>
        <div className="ml-3 hidden overflow-hidden lg:block">
          <div className="truncate text-base font-bold tracking-tight text-[#FAFAFA]">RepoPilot</div>
          <div className="truncate text-[10px] font-semibold uppercase tracking-widest text-zinc-400">
            AI Engineer
          </div>
        </div>
      </div>

      <div className="hidden border-b border-[#27272A] p-4 lg:block">
        <button
          type="button"
          onClick={onOpenCreateTask}
          className="flex w-full items-center justify-center gap-2 rounded-xl bg-blue-600 px-4 py-2.5 text-xs font-semibold uppercase tracking-wider text-white shadow-[0_0_20px_rgba(37,99,235,0.35)] transition-colors hover:bg-blue-500"
        >
          <Plus className="h-4 w-4" />
          <span>New Task</span>
        </button>
      </div>

      <div className="flex justify-center border-b border-[#27272A] p-2 lg:hidden">
        <button
          type="button"
          onClick={onOpenCreateTask}
          className="flex h-10 w-10 items-center justify-center rounded-xl bg-blue-600 text-white shadow-[0_0_15px_rgba(37,99,235,0.3)] transition-colors hover:bg-blue-500"
          title="New Task"
        >
          <Plus className="h-5 w-5" />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto py-3">
        <ul className="space-y-1.5 px-2.5 text-xs font-semibold tracking-wide">
          {navItems.map((item) => {
            const active =
              pathname === item.href ||
              (item.href === "/tasks" && pathname.startsWith("/tasks/"));
            const Icon = item.icon;

            return (
              <li key={item.href}>
                <Link
                  href={item.href}
                  aria-current={active ? "page" : undefined}
                  className={`flex w-full items-center gap-3 rounded-xl p-2.5 transition-colors ${
                    active
                      ? "border-l-2 border-blue-500 bg-[#27272A] text-white shadow-sm"
                      : "text-zinc-400 hover:bg-[#27272A]/50 hover:text-white"
                  }`}
                >
                  <Icon className={`h-4 w-4 shrink-0 ${item.color}`} />
                  <span className="hidden lg:block">{item.label}</span>
                </Link>
              </li>
            );
          })}
        </ul>
      </div>
      <div className="mt-auto border-t border-[#27272A] p-2.5">
        <div className="hidden lg:block">
          <div className="mb-2 min-w-0 rounded-lg bg-[#212124] px-3 py-2">
            <p className="truncate text-xs font-semibold text-zinc-200">
              {displayName}
            </p>
            <p className="mt-0.5 truncate text-[10px] text-zinc-500">
              @{user.github_login}
            </p>
          </div>
          <button
            type="button"
            onClick={onLogout}
            disabled={isLoggingOut}
            className="flex w-full items-center justify-center gap-2 rounded-lg border border-[#303036] px-3 py-2 text-xs font-semibold text-zinc-400 transition-colors hover:border-rose-400/30 hover:bg-rose-500/10 hover:text-rose-300 disabled:cursor-wait disabled:opacity-50"
          >
            <LogOut className="h-3.5 w-3.5" />
            {isLoggingOut ? "Signing out..." : "Sign out"}
          </button>
        </div>
        <button
          type="button"
          onClick={onLogout}
          disabled={isLoggingOut}
          aria-label={isLoggingOut ? "Signing out" : "Sign out"}
          title={isLoggingOut ? "Signing out..." : "Sign out"}
          className="flex h-10 w-10 items-center justify-center rounded-lg text-zinc-400 transition-colors hover:bg-rose-500/10 hover:text-rose-300 disabled:cursor-wait disabled:opacity-50 lg:hidden"
        >
          <LogOut className="h-4 w-4" />
        </button>
      </div>
    </nav>
  );
}
