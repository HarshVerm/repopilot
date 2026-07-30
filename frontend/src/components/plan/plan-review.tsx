"use client";

// Module purpose: Render and coordinate the plan review interface.

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  ArrowRight,
  Brain,
  FileText,
  FolderOpen,
  ListOrdered,
  MessageSquareText,
  SearchCode,
} from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { approvePlan, getPlan, rejectPlan } from "@/lib/api/plans";
import { isApiError } from "@/lib/api/client";
import { restartTask } from "@/lib/api/tasks";
import { canApprovePlan, planNeedsClarification } from "@/lib/plan-state";
import { queryKeys } from "@/lib/query-client";
import type { TaskResponse } from "@/types/api";
import { ConfirmationDialog } from "@/components/shared/confirmation-dialog";
import { EmptyState } from "@/components/shared/empty-state";
import { ErrorState } from "@/components/shared/error-state";
import { LoadingState } from "@/components/shared/loading-state";
import { StatusBadge } from "@/components/shared/status-badge";

/** Purpose: Render the plan review interface. */
export function PlanReview({ task }: { task: TaskResponse }) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [confirmReject, setConfirmReject] = useState(false);
  const [reason, setReason] = useState("");
  const [clarification, setClarification] = useState("");
  const [conflict, setConflict] = useState<string | null>(null);

  const planQuery = useQuery({
    queryKey: task.active_plan_id ? queryKeys.plan(task.active_plan_id) : ["plan", "none"],
    queryFn: ({ signal }) => getPlan(task.active_plan_id!, signal),
    enabled: Boolean(task.active_plan_id),
  });

  /** Purpose: Invalidate module state for this frontend workflow. */
  const invalidate = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: queryKeys.task(task.task_id) }),
      queryClient.invalidateQueries({ queryKey: queryKeys.taskTimeline(task.task_id) }),
      task.active_plan_id
        ? queryClient.invalidateQueries({ queryKey: queryKeys.plan(task.active_plan_id) })
        : Promise.resolve(),
      queryClient.invalidateQueries({ queryKey: queryKeys.tasks }),
    ]);
  };

  const approveMutation = useMutation({
    mutationFn: () => approvePlan(task.active_plan_id!),
    onSuccess: invalidate,
    onError: async (error) => {
      if (isApiError(error) && error.status === 409) {
        setConflict(error.message);
        await invalidate();
      }
    },
  });

  const rejectMutation = useMutation({
    mutationFn: () => rejectPlan(task.active_plan_id!, reason.trim() || undefined),
    onSuccess: async () => {
      setConfirmReject(false);
      setReason("");
      await invalidate();
    },
    onError: async (error) => {
      if (isApiError(error) && error.status === 409) {
        setConflict(error.message);
        await invalidate();
      }
    },
  });

  const clarificationMutation = useMutation({
    mutationFn: () =>
      restartTask(task.task_id, {
        clarification: clarification.trim(),
      }),
    onSuccess: async (restartedTask) => {
      queryClient.setQueryData(
        queryKeys.task(restartedTask.task_id),
        restartedTask,
      );
      await Promise.all([
        queryClient.invalidateQueries({
          queryKey: queryKeys.task(task.task_id),
        }),
        queryClient.invalidateQueries({
          queryKey: queryKeys.taskTimeline(task.task_id),
        }),
        queryClient.invalidateQueries({
          queryKey: queryKeys.tasks,
        }),
      ]);
      router.push(
        `/tasks/${restartedTask.task_id}?tab=plan`,
      );
    },
  });

  if (!task.active_plan_id) {
    if (task.status === "plan_revision_required") {
      return (
        <div className="rounded-xl border border-rose-500/30 bg-rose-500/10 p-5">
          <div className="flex items-start gap-3">
            <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-rose-400" />
            <div>
              <h2 className="text-sm font-semibold text-rose-300">
                Planning stopped before a valid plan was saved
              </h2>
              <p className="mt-1 text-xs leading-relaxed text-rose-100">
                {task.last_error ??
                  "The planner output did not pass RepoPilot's validation rules."}
              </p>
            </div>
          </div>
        </div>
      );
    }
    return <EmptyState title="No plan yet" detail="The planner has not generated a plan for this task." />;
  }

  if (planQuery.isLoading) {
    return <LoadingState title="Loading plan" rows={6} />;
  }

  if (planQuery.isError) {
    return <ErrorState error={planQuery.error} onRetry={() => planQuery.refetch()} />;
  }

  const plan = planQuery.data;
  if (!plan) {
    return <EmptyState title="No plan yet" />;
  }

  const needsClarification = planNeedsClarification(plan);
  const canApprove = canApprovePlan(task.status, plan);
  const mutationPending =
    approveMutation.isPending ||
    rejectMutation.isPending ||
    clarificationMutation.isPending;

  return (
    <div className="mx-auto flex max-w-5xl flex-col gap-4">
      <div className="flex items-end justify-between border-b border-[#30363D] pb-3">
        <div>
          <h1 className="mb-0.5 text-lg font-bold text-[#dae3ee]">Review Execution Plan</h1>
          <p className="flex items-center gap-1 text-xs text-[#c1c6d6]">
            Task <span className="font-code">{task.task_id}</span>
            <ArrowRight className="h-3.5 w-3.5 text-[#acc7ff]" />
            Issue #{task.issue_number}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <StatusBadge status={plan.status} />
          <div className="flex items-center gap-2 rounded border border-[#30363D] bg-[#182028] px-3 py-1.5">
            <Brain className="h-4 w-4 text-[#ffb68b]" />
            <span className="font-code text-xs font-bold text-[#ffb68b]">
              {Math.round(plan.plan.confidence * 100)}% Confidence
            </span>
          </div>
        </div>
      </div>

      {conflict ? (
        <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 p-4 text-sm text-amber-100">
          <h2 className="font-semibold text-amber-300">Plan state changed</h2>
          <p className="mt-1 text-xs leading-relaxed">{conflict}</p>
        </div>
      ) : null}

      {needsClarification ? (
        <section className="rounded-xl border border-amber-500/30 bg-amber-500/10 p-5">
          <div className="flex items-start gap-3">
            <MessageSquareText className="mt-0.5 h-5 w-5 shrink-0 text-amber-300" />
            <div className="min-w-0 flex-1">
              <h2 className="text-sm font-semibold text-amber-200">
                More context required
              </h2>
              <p className="mt-1 text-xs leading-relaxed text-amber-100/80">
                The planner cannot safely implement this issue yet. Answer the
                questions below, then RepoPilot will create a new planning
                attempt. This task remains available as history.
              </p>

              <ol className="mt-4 space-y-2 text-xs text-amber-50">
                {plan.plan.missing_context.length > 0 ? (
                  plan.plan.missing_context.map((question, index) => (
                    <li
                      key={question}
                      className="flex gap-2 rounded-lg border border-amber-500/20 bg-black/20 p-3"
                    >
                      <span className="font-code text-amber-300">
                        {index + 1}.
                      </span>
                      <span>{question}</span>
                    </li>
                  ))
                ) : (
                  <li>
                    Explain the intended behavior and any implementation
                    constraints the planner should follow.
                  </li>
                )}
              </ol>

              <form
                className="mt-4"
                onSubmit={(event) => {
                  event.preventDefault();
                  if (
                    clarification.trim() &&
                    !clarificationMutation.isPending
                  ) {
                    clarificationMutation.mutate();
                  }
                }}
              >
                <label
                  htmlFor="planner-clarification"
                  className="text-xs font-semibold text-amber-100"
                >
                  Your clarification
                </label>
                <textarea
                  id="planner-clarification"
                  value={clarification}
                  onChange={(event) =>
                    setClarification(event.target.value)
                  }
                  maxLength={10_000}
                  rows={5}
                  placeholder="Answer each question with the expected behavior, source of truth, and any constraints."
                  className="mt-2 w-full resize-y rounded-lg border border-amber-500/30 bg-[#060f16] px-3 py-2 text-sm leading-relaxed text-[#dae3ee] outline-none transition-colors placeholder:text-zinc-600 focus:border-amber-300"
                />
                <div className="mt-2 flex flex-wrap items-center justify-between gap-3">
                  <span className="font-code text-[10px] text-amber-100/60">
                    {clarification.length}/10000
                  </span>
                  <button
                    type="submit"
                    disabled={
                      !clarification.trim() ||
                      clarificationMutation.isPending
                    }
                    className="rounded bg-amber-300 px-4 py-2 text-xs font-bold uppercase tracking-wider text-amber-950 transition-colors hover:bg-amber-200 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    {clarificationMutation.isPending
                      ? "Starting New Plan..."
                      : "Submit Context & Replan"}
                  </button>
                </div>
              </form>

              {clarificationMutation.isError ? (
                <div className="mt-4">
                  <ErrorState
                    error={clarificationMutation.error}
                  />
                </div>
              ) : null}
            </div>
          </div>
        </section>
      ) : null}

      <div className="grid grid-cols-1 gap-3 overflow-hidden rounded border border-[#30363D] bg-[#30363D] md:grid-cols-3">
        <section className="flex flex-col gap-2.5 bg-[#161B22] p-4 md:col-span-2">
          <h2 className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-widest text-[#c1c6d6]">
            <SearchCode className="h-4 w-4 text-[#acc7ff]" />
            Problem Analysis & Root Cause
          </h2>
          <div className="space-y-3 rounded border border-[#30363D] bg-[#060f16] p-3 text-xs leading-relaxed text-[#dae3ee]">
            <p>{plan.plan.summary || "Not provided"}</p>
            <p>{plan.plan.problem_analysis || "Not provided"}</p>
            <p>
              <strong>Likely root cause:</strong> {plan.plan.likely_root_cause || "Not provided"}
            </p>
          </div>
        </section>

        <section className="flex flex-col gap-2.5 bg-[#161B22] p-4">
          <h2 className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-widest text-[#c1c6d6]">
            <FolderOpen className="h-4 w-4 text-[#acc7ff]" />
            Files to Modify
          </h2>
          <ul className="flex flex-col gap-2 text-xs font-code text-[#dae3ee]">
            {plan.plan.files_to_modify.length > 0 ? (
              plan.plan.files_to_modify.map((file) => (
                <li key={file.path} className="rounded border border-[#30363D] bg-[#060f16] p-2">
                  <div className="flex items-center gap-2">
                    <FileText className="h-3.5 w-3.5 text-[#acc7ff]" />
                    <span className="truncate" title={file.path}>
                      {file.path}
                    </span>
                    {file.change_type === "create" ? (
                      <span className="rounded border border-emerald-500/30 bg-emerald-500/10 px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wider text-emerald-300">
                        New
                      </span>
                    ) : null}
                  </div>
                  <p className="mt-1 truncate text-[11px] text-zinc-500" title={file.reason}>
                    {file.reason}
                  </p>
                </li>
              ))
            ) : (
              <li className="text-zinc-500">Not provided</li>
            )}
          </ul>
        </section>

        <section className="flex flex-col gap-2.5 bg-[#161B22] p-4 md:col-span-3">
          <h2 className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-widest text-[#c1c6d6]">
            <ListOrdered className="h-4 w-4 text-[#acc7ff]" />
            Implementation Steps
          </h2>
          <div className="divide-y divide-[#30363D] overflow-hidden rounded border border-[#30363D]">
            {plan.plan.implementation_steps.length > 0 ? (
              plan.plan.implementation_steps.map((item) => (
                <div key={item.order} className="flex items-start gap-3 bg-[#060f16] p-3">
                  <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded border border-[#30363D] bg-[#2d363e] font-code text-xs font-bold text-[#dae3ee]">
                    {item.order}
                  </span>
                  <div className="min-w-0 text-xs leading-normal text-[#dae3ee]">
                    <p>{item.description}</p>
                    {item.files.length > 0 ? (
                      <p className="mt-1 truncate font-code text-[11px] text-zinc-500">
                        {item.files.join(", ")}
                      </p>
                    ) : null}
                  </div>
                </div>
              ))
            ) : (
              <div className="bg-[#060f16] p-3 text-xs text-zinc-500">Not provided</div>
            )}
          </div>
        </section>

        <section className="flex flex-col gap-2.5 border-t border-[#e47014] bg-[#1d1912] p-4 md:col-span-3">
          <h2 className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-widest text-[#ffb68b]">
            <AlertTriangle className="h-4 w-4 text-[#e47014]" />
            Tests, Risks & Assumptions
          </h2>
          <div className="grid grid-cols-1 gap-4 text-xs leading-relaxed text-[#ffb68b] md:grid-cols-3">
            <List title="Test Plan" items={plan.plan.tests.map((test) => `${test.test_type}: ${test.description}`)} />
            <List title="Risks" items={plan.plan.risks} />
            <List title="Missing Context" items={plan.plan.missing_context} fallback={plan.plan.needs_more_context ? "Not provided" : "No missing context reported"} />
          </div>
        </section>
      </div>

      {canApprove ? (
        <div className="sticky bottom-0 z-40 flex items-center justify-between gap-4 border-t border-[#30363D] bg-[#060f16] px-6 py-3 shadow-lg">
          <p className="hidden text-xs text-[#c1c6d6] sm:block">
            Approving the plan permits RepoPilot to continue with the approved scope.
          </p>
          <div className="ml-auto flex gap-3">
            <button
              type="button"
              onClick={() => setConfirmReject(true)}
              disabled={mutationPending}
              className="rounded border border-[#30363D] px-4 py-2 text-xs font-semibold uppercase tracking-wider text-[#dae3ee] transition-colors hover:bg-[#182028] disabled:opacity-50"
            >
              Reject Plan
            </button>
            <button
              type="button"
              onClick={() => approveMutation.mutate()}
              disabled={mutationPending}
              className="rounded bg-[#acc7ff] px-4 py-2 text-xs font-bold uppercase tracking-wider text-[#002f68] shadow-sm transition-colors hover:bg-[#d7e2ff] disabled:opacity-50"
            >
              {approveMutation.isPending ? "Approving..." : "Approve Plan"}
            </button>
          </div>
        </div>
      ) : null}

      <ConfirmationDialog
        open={confirmReject}
        title="Reject execution plan?"
        description="RepoPilot will keep the task history and stop coding for this plan."
        confirmLabel="Reject Plan"
        variant="danger"
        pending={rejectMutation.isPending}
        reason={reason}
        onReasonChange={setReason}
        onCancel={() => setConfirmReject(false)}
        onConfirm={() => rejectMutation.mutate()}
      />
    </div>
  );
}

/** Purpose: Render the list interface. */
function List({
  title,
  items,
  fallback = "Not provided",
}: {
  title: string;
  items: string[];
  fallback?: string;
}) {
  return (
    <div className="border-l-2 border-[#e47014] pl-3">
      <h3 className="mb-1 font-semibold">{title}</h3>
      {items.length > 0 ? (
        <ul className="space-y-1">
          {items.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      ) : (
        <p>{fallback}</p>
      )}
    </div>
  );
}
