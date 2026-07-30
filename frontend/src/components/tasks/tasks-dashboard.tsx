"use client";

// Module purpose: Render and coordinate the tasks dashboard interface.

import { useQuery } from "@tanstack/react-query";
import { ChevronDown, RefreshCw } from "lucide-react";
import { useMemo, useState } from "react";
import { PageHeader } from "@/components/app-shell/page-header";
import { EmptyState } from "@/components/shared/empty-state";
import { ErrorState } from "@/components/shared/error-state";
import { LoadingState } from "@/components/shared/loading-state";
import { listTasks } from "@/lib/api/tasks";
import { repositoryFullName } from "@/lib/formatters";
import { queryKeys } from "@/lib/query-client";
import { isActiveTask, isWaitingForHuman } from "@/lib/task-status";
import type { TaskResponse } from "@/types/api";
import { TaskTable } from "./task-table";

type StatusFilter = "All" | "Active" | "Waiting for Me" | "Failed" | "Completed";

/** Purpose: Filter by status for this frontend workflow. */
function filterByStatus(task: TaskResponse, status: StatusFilter) {
  if (status === "All") return true;
  if (status === "Active") return isActiveTask(task);
  if (status === "Waiting for Me") return isWaitingForHuman(task);
  if (status === "Failed") return task.status === "failed";
  if (status === "Completed") return task.status === "completed";
  return true;
}

/** Purpose: Render the stat card interface. */
function StatCard({
  label,
  value,
  detail,
  tone,
  pulse,
}: {
  label: string;
  value: number;
  detail: string;
  tone: "blue" | "amber" | "rose" | "emerald";
  pulse?: boolean;
}) {
  const colors = {
    blue: "text-blue-400 border-blue-500/20 bg-blue-500/10",
    amber: "text-amber-400 border-amber-500/20 bg-amber-500/10",
    rose: "text-rose-400 border-rose-500/20 bg-rose-500/10",
    emerald: "text-emerald-400 border-emerald-500/20 bg-emerald-500/10",
  };

  return (
    <div className="flex flex-col justify-between rounded-2xl border border-[#27272A] bg-[#18181B] p-5 transition-colors hover:border-blue-500/40">
      <div className="flex items-center justify-between text-zinc-400">
        <span className="text-[11px] font-semibold uppercase tracking-widest">{label}</span>
        <div className={`flex h-8 w-8 items-center justify-center rounded-xl border ${colors[tone]}`}>
          <span className={`h-2.5 w-2.5 rounded-full bg-current ${pulse ? "animate-pulse" : ""}`} />
        </div>
      </div>
      <div className="mt-4">
        <div className="text-3xl font-bold tracking-tight text-[#FAFAFA]">{value}</div>
        <p className={`mt-1 text-xs font-medium ${colors[tone].split(" ")[0]}`}>{detail}</p>
      </div>
    </div>
  );
}

/** Purpose: Render the tasks dashboard interface. */
export function TasksDashboard() {
  const [searchQuery, setSearchQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("All");
  const [repoFilter, setRepoFilter] = useState("All");
  const query = useQuery({
    queryKey: queryKeys.tasks,
    queryFn: ({ signal }) => listTasks(signal),
    refetchInterval: (taskQuery) =>
      taskQuery.state.data?.tasks.some((task) => isActiveTask(task)) ? 3000 : false,
  });

  const tasks = useMemo(() => query.data?.tasks ?? [], [query.data?.tasks]);
  const repositories = useMemo(
    () => Array.from(new Set(tasks.map(repositoryFullName))).sort(),
    [tasks],
  );

  const counts = useMemo(
    () => ({
      active: tasks.filter(isActiveTask).length,
      waiting: tasks.filter(isWaitingForHuman).length,
      failed: tasks.filter((task) => task.status === "failed").length,
      completed: tasks.filter((task) => task.status === "completed").length,
    }),
    [tasks],
  );

  const filteredTasks = useMemo(() => {
    const queryText = searchQuery.trim().toLowerCase();
    return tasks.filter((task) => {
      if (!filterByStatus(task, statusFilter)) return false;
      if (repoFilter !== "All" && repositoryFullName(task) !== repoFilter) return false;
      if (!queryText) return true;

      return (
        task.task_id.toLowerCase().includes(queryText) ||
        (task.issue?.title?.toLowerCase().includes(queryText) ?? false) ||
        repositoryFullName(task).toLowerCase().includes(queryText) ||
        String(task.issue_number).includes(queryText) ||
        task.status.toLowerCase().includes(queryText)
      );
    });
  }, [repoFilter, searchQuery, statusFilter, tasks]);

  return (
    <>
      <PageHeader
        title="Tasks"
        subtitle="RepoPilot task lifecycle console"
        search={searchQuery}
        onSearchChange={setSearchQuery}
      />
      <div className="flex-1 space-y-6 overflow-y-auto p-4 md:p-6">
        <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
          <StatCard label="Active Tasks" value={counts.active} detail="Executing now" tone="blue" pulse />
          <StatCard label="Needs Review" value={counts.waiting} detail="Awaiting approval" tone="amber" />
          <StatCard label="Failed" value={counts.failed} detail="Needs diagnosis" tone="rose" />
          <StatCard label="Completed" value={counts.completed} detail="PR workflows done" tone="emerald" />
        </div>

        <div className="flex min-h-[calc(100vh-280px)] flex-col rounded-2xl border border-[#27272A] bg-[#18181B] p-4 shadow-2xl md:p-6">
          <div className="mb-4 flex shrink-0 items-center justify-between gap-4 border-b border-[#27272A] pb-4">
            <div className="flex min-w-0 flex-wrap items-center gap-3">
              <div className="relative">
                <select
                  value={statusFilter}
                  onChange={(event) => setStatusFilter(event.target.value as StatusFilter)}
                  className="h-9 appearance-none rounded-xl border border-[#3F3F46] bg-[#27272A] pl-3 pr-8 text-xs font-medium text-[#FAFAFA]"
                >
                  <option value="All">Status: All</option>
                  <option value="Active">Active</option>
                  <option value="Waiting for Me">Waiting for Me</option>
                  <option value="Failed">Failed</option>
                  <option value="Completed">Completed</option>
                </select>
                <ChevronDown className="pointer-events-none absolute right-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-zinc-400" />
              </div>

              <div className="relative">
                <select
                  value={repoFilter}
                  onChange={(event) => setRepoFilter(event.target.value)}
                  className="h-9 max-w-56 appearance-none rounded-xl border border-[#3F3F46] bg-[#27272A] pl-3 pr-8 text-xs font-medium text-[#FAFAFA]"
                >
                  <option value="All">Repository: All</option>
                  {repositories.map((repository) => (
                    <option key={repository} value={repository}>
                      {repository}
                    </option>
                  ))}
                </select>
                <ChevronDown className="pointer-events-none absolute right-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-zinc-400" />
              </div>
            </div>

            <button
              type="button"
              onClick={() => query.refetch()}
              disabled={query.isFetching}
              className="rounded-xl border border-[#3F3F46] bg-[#27272A] p-2 text-zinc-400 transition-colors hover:bg-[#3F3F46] hover:text-white disabled:opacity-50"
              title="Refresh"
            >
              <RefreshCw className={`h-4 w-4 ${query.isFetching ? "animate-spin text-blue-400" : ""}`} />
            </button>
          </div>

          {query.isLoading ? <LoadingState title="Loading tasks" rows={6} /> : null}
          {query.isError ? <ErrorState error={query.error} onRetry={() => query.refetch()} /> : null}
          {query.isSuccess && tasks.length === 0 ? (
            <EmptyState
              title="No RepoPilot tasks yet."
              detail="Create a task from a GitHub issue to begin."
            />
          ) : null}
          {query.isSuccess && tasks.length > 0 && filteredTasks.length === 0 ? (
            <EmptyState title="No tasks match these filters." />
          ) : null}
          {query.isSuccess && filteredTasks.length > 0 ? <TaskTable tasks={filteredTasks} /> : null}
        </div>
      </div>
    </>
  );
}
