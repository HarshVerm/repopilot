"use client";

import type { TaskTab } from "@/types/task";

const tabs: Array<{ id: TaskTab; label: string }> = [
  { id: "overview", label: "Overview" },
  { id: "plan", label: "Plan" },
  { id: "changes", label: "Changes" },
  { id: "verification", label: "Verification" },
  { id: "debug", label: "Debug" },
  { id: "timeline", label: "Timeline" },
  { id: "metrics", label: "Metrics" },
];

export function TaskTabs({
  activeTab,
  onTabChange,
}: {
  activeTab: TaskTab;
  onTabChange: (tab: TaskTab) => void;
}) {
  return (
    <div className="flex h-12 shrink-0 items-center justify-between border-b border-[#27272A] bg-[#18181B] px-6">
      <div className="flex h-full gap-6 overflow-x-auto">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            type="button"
            onClick={() => onTabChange(tab.id)}
            className={`flex h-full shrink-0 items-center border-b-2 text-xs font-semibold uppercase tracking-wider transition-colors ${
              activeTab === tab.id
                ? "border-blue-500 text-blue-400"
                : "border-transparent text-zinc-400 hover:text-white"
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>
    </div>
  );
}

export function normalizeTaskTab(value: string | null): TaskTab {
  return tabs.some((tab) => tab.id === value) ? (value as TaskTab) : "overview";
}
