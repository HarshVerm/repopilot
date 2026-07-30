"use client";

// Module purpose: Render and coordinate the page header interface.

import type { ReactNode } from "react";
import { Search } from "lucide-react";

/** Purpose: Render the page header interface. */
export function PageHeader({
  title,
  subtitle,
  search,
  onSearchChange,
  rightAction,
}: {
  title: string;
  subtitle?: string;
  search?: string;
  onSearchChange?: (value: string) => void;
  rightAction?: ReactNode;
}) {
  return (
    <header className="flex min-h-16 shrink-0 items-center justify-between gap-4 border-b border-[#27272A] bg-[#18181B] px-6 py-3">
      <div className="min-w-0">
        <h1 className="truncate text-lg font-semibold tracking-tight text-[#FAFAFA]">{title}</h1>
        {subtitle ? <p className="mt-0.5 truncate text-xs text-zinc-400">{subtitle}</p> : null}
      </div>
      <div className="flex shrink-0 items-center gap-4">
        {onSearchChange ? (
          <div className="relative hidden h-9 w-64 items-center rounded-full border border-[#27272A] bg-[#09090B] px-3.5 text-zinc-400 transition-colors focus-within:border-blue-500 focus-within:ring-1 focus-within:ring-blue-500 md:flex lg:w-80">
            <Search className="mr-2 h-4 w-4 shrink-0 text-zinc-500" />
            <input
              type="text"
              value={search ?? ""}
              onChange={(event) => onSearchChange(event.target.value)}
              placeholder="Search tasks, repos, IDs..."
              className="w-full border-none bg-transparent p-0 text-xs text-[#FAFAFA] placeholder:text-zinc-500 focus:outline-none"
            />
          </div>
        ) : null}
        {rightAction}
      </div>
    </header>
  );
}
