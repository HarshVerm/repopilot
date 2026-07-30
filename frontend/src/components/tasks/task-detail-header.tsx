"use client";

// Module purpose: Render and coordinate the task detail header interface.

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ExternalLink, Folder, RefreshCw } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { cancelTask, restartTask } from "@/lib/api/tasks";
import { publishTask } from "@/lib/api/publications";
import { errorMessage } from "@/lib/errors";
import { formatStatus, repositoryFullName } from "@/lib/formatters";
import { queryKeys } from "@/lib/query-client";
import { getAvailableTaskActions } from "@/lib/task-actions";
import { isRestartableStatus } from "@/lib/task-status";
import type { IssueResponse, PublicationResponse, TaskResponse } from "@/types/api";
import type { TaskTab } from "@/types/task";
import { ConfirmationDialog } from "@/components/shared/confirmation-dialog";
import { StatusBadge } from "@/components/shared/status-badge";
import { TaskLifecycle } from "./task-lifecycle";

/** Purpose: Render the task detail header interface. */
export function TaskDetailHeader({
  task,
  issue,
  publication,
  onTabChange,
  onRefresh,
  refreshing,
}: {
  task: TaskResponse;
  issue?: IssueResponse;
  publication?: PublicationResponse | null;
  onTabChange: (tab: TaskTab) => void;
  onRefresh: () => void;
  refreshing?: boolean;
}) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [confirmCancel, setConfirmCancel] = useState(false);
  const [confirmRestart, setConfirmRestart] = useState(false);
  const actions = getAvailableTaskActions(task, publication);
  const restartable = isRestartableStatus(task.status);
  const needsPlannerContext =
    task.status === "plan_revision_required" &&
    task.last_error_type === "PlannerNeedsMoreContext";

  const cancelMutation = useMutation({
    mutationFn: () => cancelTask(task.task_id),
    onSuccess: async () => {
      setConfirmCancel(false);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.task(task.task_id) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.taskTimeline(task.task_id) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.tasks }),
      ]);
    },
  });

  const publishMutation = useMutation({
    mutationFn: () => publishTask(task.task_id),
    onSuccess: async (result) => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.task(task.task_id) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.taskTimeline(task.task_id) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.reviewPublication(task.active_review_id!) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.publication(result.publication_id) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.tasks }),
      ]);
      onTabChange("changes");
    },
    onError: async (error) => {
      if (typeof error === "object" && error && "status" in error && (error as { status: number }).status === 409) {
        await Promise.all([
          queryClient.invalidateQueries({ queryKey: queryKeys.task(task.task_id) }),
          task.active_review_id
            ? queryClient.invalidateQueries({ queryKey: queryKeys.reviewPublication(task.active_review_id) })
            : Promise.resolve(),
        ]);
      }
    },
  });

  const restartMutation = useMutation({
    mutationFn: () => restartTask(task.task_id),
    onSuccess: async (restartedTask) => {
      setConfirmRestart(false);
      queryClient.setQueryData(
        queryKeys.task(restartedTask.task_id),
        restartedTask,
      );
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.task(task.task_id) }),
        queryClient.invalidateQueries({
          queryKey: queryKeys.taskTimeline(task.task_id),
        }),
        queryClient.invalidateQueries({ queryKey: queryKeys.tasks }),
      ]);
      router.push(`/tasks/${restartedTask.task_id}`);
    },
  });

  /** Purpose: Handle run action for this frontend module. */
  function runAction(actionId: string) {
    if (actionId === "review_plan") onTabChange("plan");
    if (actionId === "review_final_diff") onTabChange("changes");
    if (actionId === "cancel_task") setConfirmCancel(true);
    if (actionId === "publish_pull_request" && task.active_review_id) publishMutation.mutate();
    if (actionId === "open_pull_request" && publication?.pull_request_url) {
      window.open(publication.pull_request_url, "_blank", "noopener,noreferrer");
    }
  }

  return (
    <header className="shrink-0 border-b border-[#27272A] bg-[#18181B] px-6 py-4">
      <div className="mb-3 flex items-center justify-between gap-3 text-xs text-zinc-400">
        <div className="flex min-w-0 items-center gap-2">
          <Link href="/tasks" className="hover:text-white">
            Tasks
          </Link>
          <span className="text-zinc-600">/</span>
          <span className="truncate font-code font-semibold text-[#FAFAFA]">{task.task_id}</span>
        </div>
        <StatusBadge status={task.status} />
      </div>

      <div className="flex flex-col justify-between gap-4 lg:flex-row lg:items-start">
        <div className="min-w-0">
          <h1 className="truncate text-xl font-bold text-[#FAFAFA]">
            {issue?.title ?? `GitHub Issue #${task.issue_number}`}
          </h1>
          <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-zinc-400">
            <span className="flex min-w-0 items-center gap-2 font-code">
              <Folder className="h-4 w-4 text-zinc-500" />
              <span className="truncate">{repositoryFullName(task)}</span>
            </span>
            <span className="font-code">Issue #{task.issue_number}</span>
            <span className="font-code">Task {task.task_id}</span>
            <span>{formatStatus(task.status)}</span>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={() => {
              if (needsPlannerContext) {
                onTabChange("plan");
                return;
              }
              if (restartable) {
                restartMutation.reset();
                setConfirmRestart(true);
                return;
              }
              onRefresh();
            }}
            disabled={restartMutation.isPending}
            className="rounded-xl border border-[#3F3F46] bg-[#27272A] p-2 text-zinc-400 transition-colors hover:bg-[#3F3F46] hover:text-white"
            title={
              needsPlannerContext
                ? "Provide missing plan context"
                : restartable
                  ? "Restart task"
                  : "Refresh state"
            }
            aria-label={
              needsPlannerContext
                ? "Provide missing plan context"
                : restartable
                  ? "Restart task"
                  : "Refresh state"
            }
          >
            <RefreshCw
              className={`h-4 w-4 ${
                refreshing || restartMutation.isPending
                  ? "animate-spin text-blue-400"
                  : restartable
                    ? "text-blue-400"
                    : ""
              }`}
            />
          </button>
          {issue?.html_url ? (
            <a
              href={issue.html_url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-2 rounded-xl border border-[#3F3F46] bg-[#27272A] px-3.5 py-2 text-xs font-semibold uppercase tracking-wider text-[#FAFAFA] transition-colors hover:bg-[#3F3F46]"
            >
              <ExternalLink className="h-3.5 w-3.5" />
              GitHub Issue
            </a>
          ) : null}
          {actions.map((action) => (
            <button
              key={action.id}
              type="button"
              onClick={() => runAction(action.id)}
              disabled={action.disabled || cancelMutation.isPending || publishMutation.isPending}
              className={`rounded-xl px-3.5 py-2 text-xs font-semibold uppercase tracking-wider transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${
                action.kind === "primary"
                  ? "bg-blue-600 text-white shadow-[0_0_15px_rgba(37,99,235,0.35)] hover:bg-blue-500"
                  : action.kind === "danger"
                    ? "text-rose-400 hover:bg-rose-500/10"
                    : "border border-[#3F3F46] bg-[#27272A] text-[#FAFAFA] hover:bg-[#3F3F46]"
              }`}
            >
              {action.id === "publish_pull_request" && publishMutation.isPending
                ? "Publishing..."
                : action.label}
            </button>
          ))}
        </div>
      </div>

      <TaskLifecycle task={task} />

      <ConfirmationDialog
        open={confirmRestart}
        title="Restart this task?"
        description="RepoPilot will create a new execution attempt for the same GitHub issue, fetch the latest repository state, and keep this task and its timeline as history."
        confirmLabel="Restart Task"
        pending={restartMutation.isPending}
        error={
          restartMutation.isError
            ? errorMessage(restartMutation.error)
            : undefined
        }
        onCancel={() => {
          if (!restartMutation.isPending) {
            setConfirmRestart(false);
            restartMutation.reset();
          }
        }}
        onConfirm={() => restartMutation.mutate()}
      />

      <ConfirmationDialog
        open={confirmCancel}
        title="Cancel RepoPilot task?"
        description="This stops further execution. Existing task history will remain available."
        confirmLabel="Cancel Task"
        variant="danger"
        pending={cancelMutation.isPending}
        onCancel={() => setConfirmCancel(false)}
        onConfirm={() => cancelMutation.mutate()}
      />
    </header>
  );
}
