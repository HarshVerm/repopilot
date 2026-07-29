"use client";

import { useQuery } from "@tanstack/react-query";
import { Bug } from "lucide-react";
import type { TaskResponse } from "@/types/api";
import { getFinalReview } from "@/lib/api/reviews";
import { queryKeys } from "@/lib/query-client";
import { EmptyState } from "@/components/shared/empty-state";
import { ErrorState } from "@/components/shared/error-state";
import { LoadingState } from "@/components/shared/loading-state";
import { StatusBadge } from "@/components/shared/status-badge";

interface DebugAttempt {
  debug_attempt_id?: string;
  attempt?: number;
  failure_category?: string;
  status?: string;
  parent_change_set_id?: string;
  new_change_set_id?: string | null;
  retry_execution_run_id?: string | null;
  diagnosis?: string | null;
  stop_reason?: string | null;
  needs_plan_revision?: boolean;
}

export function DebugAttemptList({ task }: { task: TaskResponse }) {
  const reviewQuery = useQuery({
    queryKey: task.active_review_id ? queryKeys.review(task.active_review_id) : ["review", "none"],
    queryFn: ({ signal }) => getFinalReview(task.active_review_id!, signal),
    enabled: Boolean(task.active_review_id),
  });

  if (!task.active_review_id) {
    return (
      <EmptyState
        title="No debugger attempts"
        detail="Task-scoped debugger history is available once a final review artifact exists."
      />
    );
  }

  if (reviewQuery.isLoading) {
    return <LoadingState title="Loading debugger history" rows={4} />;
  }

  if (reviewQuery.isError) {
    return <ErrorState error={reviewQuery.error} onRetry={() => reviewQuery.refetch()} />;
  }

  const debugHistory = reviewQuery.data?.debug_history ?? {};
  const attempts =
    Array.isArray(debugHistory.history) ? (debugHistory.history as DebugAttempt[]) : [];
  const count =
    typeof debugHistory.debug_attempts === "number" ? debugHistory.debug_attempts : attempts.length;

  if (attempts.length === 0) {
    return <EmptyState title="No debugger attempts were required." />;
  }

  return (
    <div className="mx-auto flex max-w-4xl flex-col gap-4">
      <div className="border-b border-[#27272A] pb-3">
        <h2 className="flex items-center gap-2 text-base font-bold text-[#FAFAFA]">
          <Bug className="h-5 w-5 text-amber-400" />
          Debugger Repair Trace
        </h2>
        <p className="mt-1 text-xs text-zinc-400">Debugger Attempt {count} of 3</p>
      </div>
      {attempts.map((attempt) => (
        <article
          key={attempt.debug_attempt_id ?? attempt.attempt}
          className="rounded-lg border border-[#30363D] bg-[#141c24] p-4"
        >
          <div className="flex items-center justify-between gap-3">
            <span className="text-xs text-[#c1c6d6]">Attempt #{attempt.attempt ?? "—"}</span>
            <StatusBadge status={attempt.status ?? "unknown"} />
          </div>
          <p className="mt-3 text-xs leading-relaxed text-[#dae3ee]">
            {attempt.diagnosis ?? attempt.failure_category ?? "No diagnosis provided."}
          </p>
          <dl className="mt-3 grid grid-cols-1 gap-2 font-code text-[11px] text-zinc-400 md:grid-cols-2">
            <Pair label="Parent Change Set" value={attempt.parent_change_set_id ?? "—"} />
            <Pair label="New Change Set" value={attempt.new_change_set_id ?? "—"} />
            <Pair label="Retry Run" value={attempt.retry_execution_run_id ?? "—"} />
            <Pair label="Stop Reason" value={attempt.stop_reason ?? "—"} />
          </dl>
          {attempt.needs_plan_revision ? (
            <div className="mt-3 rounded border border-amber-500/30 bg-amber-500/10 p-3 text-xs text-amber-100">
              RepoPilot cannot modify additional files without returning to planner scope.
            </div>
          ) : null}
        </article>
      ))}
    </div>
  );
}

function Pair({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0">
      <dt className="text-zinc-500">{label}</dt>
      <dd className="truncate text-[#dae3ee]" title={value}>{value}</dd>
    </div>
  );
}
