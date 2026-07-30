// Module purpose: Render and coordinate the task overview interface.

import { Box, Bug, ClipboardCheck, Code, FileText, Info, PenTool } from "lucide-react";
import type { ReactNode } from "react";
import type { IssueResponse, PlanResponse, PublicationResponse, TaskResponse } from "@/types/api";
import { EmptyState } from "@/components/shared/empty-state";
import { StatusBadge } from "@/components/shared/status-badge";
import { formatDuration, formatNumber, metricValue, repositoryFullName } from "@/lib/formatters";
import { isActiveTask } from "@/lib/task-status";

/** Purpose: Render the task overview interface. */
export function TaskOverview({
  task,
  issue,
  plan,
  publication,
}: {
  task: TaskResponse;
  issue?: IssueResponse;
  plan?: PlanResponse;
  publication?: PublicationResponse | null;
}) {
  const agentTokens = metricValue(task.metrics, ["agent_tokens"]);
  const agentLatency = metricValue(task.metrics, ["agent_latency_ms"]);
  const durationEnd =
    task.completed_at ??
    (!isActiveTask(task) ? task.last_event_at : null);

  return (
    <div className="flex flex-col gap-6 lg:flex-row">
      <div className="flex flex-1 flex-col gap-6">
        {task.status === "plan_pending_approval" ||
        task.status === "plan_revision_required" ||
        task.status === "review_pending" ||
        task.status === "review_approved" ? (
          <div
            className={`rounded-2xl border p-5 ${
              task.status === "plan_revision_required"
                ? "border-rose-500/30 bg-rose-500/10"
                : "border-blue-500/30 bg-blue-500/10"
            }`}
          >
            <div className="flex items-start gap-3">
              <Info
                className={`mt-0.5 h-5 w-5 shrink-0 ${
                  task.status === "plan_revision_required"
                    ? "text-rose-400"
                    : "text-blue-400"
                }`}
              />
              <div>
                <h2
                  className={`text-base font-bold ${
                    task.status === "plan_revision_required"
                      ? "text-rose-300"
                      : "text-blue-400"
                  }`}
                >
                  {task.status === "plan_revision_required"
                    ? "Planning Stopped"
                    : "Action Required"}
                </h2>
                <p
                  className={`mt-1 border-l-2 py-0.5 pl-3 text-sm text-[#FAFAFA] ${
                    task.status === "plan_revision_required"
                      ? "border-rose-500"
                      : "border-blue-500"
                  }`}
                >
                  {task.status === "plan_pending_approval"
                    ? "Execution plan is waiting for human approval."
                    : task.status === "plan_revision_required"
                      ? task.last_error ??
                        "The planner could not produce a safe, valid execution plan."
                    : task.status === "review_pending"
                      ? "Final reviewed diff is waiting for human approval."
                      : "Final diff is approved. Publication still requires an explicit action."}
                </p>
              </div>
            </div>
          </div>
        ) : null}

        <div className="grid grid-cols-1 gap-6 md:grid-cols-3">
          <section className="rounded-2xl border border-[#27272A] bg-[#18181B] p-6 md:col-span-2">
            <div className="mb-4 flex items-center gap-2 border-b border-[#27272A] pb-3">
              <FileText className="h-4 w-4 text-zinc-400" />
              <h3 className="text-[11px] font-semibold uppercase tracking-widest text-zinc-400">
                Issue Summary
              </h3>
            </div>
            <h4 className="mb-2 text-lg font-bold text-[#FAFAFA]">
              {issue?.title ?? `Issue #${task.issue_number}`}
            </h4>
            <p className="text-xs leading-relaxed text-zinc-300">
              {issue?.body ?? "Issue details are unavailable from GitHub for this task."}
            </p>
            {task.issue_summary ? (
              <div className="mt-4 rounded-lg border border-[#30363D] bg-[#0D1117] p-4">
                <h5 className="text-[11px] font-semibold uppercase tracking-wider text-zinc-500">
                  RepoPilot Understanding
                </h5>
                <p className="mt-2 whitespace-pre-wrap text-xs leading-5 text-zinc-300">
                  {task.issue_summary}
                </p>
              </div>
            ) : null}
            {task.user_instructions ? (
              <div className="mt-3 rounded-lg border border-blue-500/20 bg-blue-500/5 p-3">
                <h5 className="text-[11px] font-semibold uppercase tracking-wider text-blue-300">
                  Additional Instructions
                </h5>
                <p className="mt-2 whitespace-pre-wrap text-xs leading-5 text-zinc-300">
                  {task.user_instructions}
                </p>
              </div>
            ) : null}
            <div className="mt-4 flex flex-wrap gap-2">
              <span className="rounded-full border border-[#3F3F46] bg-[#27272A] px-2.5 py-1 font-code text-[10px] text-zinc-300">
                {repositoryFullName(task)}
              </span>
              {issue?.labels.map((label) => (
                <span
                  key={label}
                  className="rounded-full border border-blue-500/30 bg-blue-500/10 px-2.5 py-1 text-[10px] font-semibold uppercase tracking-wider text-blue-400"
                >
                  {label}
                </span>
              ))}
            </div>
          </section>

          <section className="rounded-2xl border border-[#27272A] bg-[#18181B] p-6">
            <div className="mb-4 flex items-center gap-2 border-b border-[#27272A] pb-3">
              <Box className="h-4 w-4 text-zinc-400" />
              <h3 className="text-[11px] font-semibold uppercase tracking-widest text-zinc-400">
                Artifacts
              </h3>
            </div>
            <div className="flex flex-col gap-3.5 text-xs font-code">
              <Artifact label="Plan" value={task.active_plan_id ? plan?.status ?? "Available" : "No plan yet"} icon={<PenTool className="h-3.5 w-3.5 text-blue-400" />} />
              <Artifact label="Change Set" value={task.active_change_set_id ? "Available" : "No changes yet"} icon={<Code className="h-3.5 w-3.5 text-blue-400" />} />
              <Artifact label="Verification" value={task.active_execution_run_id ? "Available" : "No run yet"} icon={<ClipboardCheck className="h-3.5 w-3.5 text-emerald-400" />} />
              <Artifact label="Publication" value={publication?.status ?? "No publication yet"} icon={<Bug className="h-3.5 w-3.5 text-amber-400" />} />
            </div>
          </section>
        </div>

        {task.status === "failed" ||
        task.status === "plan_revision_required" ? (
          <section className="rounded-2xl border border-rose-500/30 bg-rose-500/10 p-5">
            <h3 className="text-sm font-semibold text-rose-300">Failure Diagnostics</h3>
            <dl className="mt-3 grid grid-cols-1 gap-3 text-xs md:grid-cols-2">
              <InfoPair label="Category" value={task.failure_category ?? "—"} />
              <InfoPair label="Retryable" value={task.retryable === null ? "—" : task.retryable ? "Yes" : "No"} />
              <InfoPair label="Error Type" value={task.last_error_type ?? "—"} />
              <InfoPair label="Last Error" value={task.last_error ?? "—"} />
            </dl>
          </section>
        ) : null}
      </div>

      <aside className="flex w-full shrink-0 flex-col gap-4 rounded-2xl border border-[#27272A] bg-[#18181B] p-6 lg:w-72">
        <h3 className="border-b border-[#27272A] pb-3 text-[11px] font-semibold uppercase tracking-widest text-zinc-400">
          Telemetry
        </h3>
        <div className="grid grid-cols-2 gap-4">
          <InfoPair label="Duration" value={formatDuration(task.started_at, durationEnd)} />
          <InfoPair label="Tokens" value={formatNumber(agentTokens)} />
          <InfoPair
            label="Latency"
            value={typeof agentLatency === "number" ? `${Math.round(agentLatency)}ms` : "—"}
          />
          <InfoPair label="Status" value={<StatusBadge status={task.status} />} />
        </div>
        {!task.active_change_set_id ? (
          <EmptyState title="No changes generated" />
        ) : null}
      </aside>
    </div>
  );
}

/** Purpose: Render the artifact interface. */
function Artifact({
  label,
  value,
  icon,
}: {
  label: string;
  value: string;
  icon: ReactNode;
}) {
  return (
    <div className="flex items-center justify-between gap-3">
      <span className="flex min-w-0 items-center gap-2 text-zinc-300">
        {icon}
        <span>{label}</span>
      </span>
      <span className="max-w-32 truncate rounded-full border border-zinc-700 bg-[#27272A] px-2.5 py-0.5 text-[11px] font-semibold text-zinc-200">
        {value}
      </span>
    </div>
  );
}

/** Purpose: Render the info pair interface. */
function InfoPair({
  label,
  value,
}: {
  label: string;
  value: ReactNode;
}) {
  return (
    <div className="min-w-0">
      <dt className="font-code text-[11px] text-zinc-500">{label}</dt>
      <dd className="mt-1 truncate font-code text-xs font-bold text-[#dae3ee]">{value}</dd>
    </div>
  );
}
