"use client";

// Module purpose: Render and coordinate the verification summary interface.

import { useQuery } from "@tanstack/react-query";
import { Terminal } from "lucide-react";
import type { TaskResponse } from "@/types/api";
import { getExecutionRun } from "@/lib/api/execution-runs";
import { queryKeys } from "@/lib/query-client";
import { EmptyState } from "@/components/shared/empty-state";
import { ErrorState } from "@/components/shared/error-state";
import { LoadingState } from "@/components/shared/loading-state";
import { StatusBadge } from "@/components/shared/status-badge";
import { CopyButton } from "@/components/shared/copy-button";

/** Purpose: Render the verification summary interface. */
export function VerificationSummary({ task }: { task: TaskResponse }) {
  const query = useQuery({
    queryKey: task.active_execution_run_id
      ? queryKeys.executionRun(task.active_execution_run_id)
      : ["executionRun", "none"],
    queryFn: ({ signal }) => getExecutionRun(task.active_execution_run_id!, signal),
    enabled: Boolean(task.active_execution_run_id),
    refetchInterval: (runQuery) => {
      const status = runQuery.state.data?.status;
      return status === "pending" || status === "running" ? 3000 : false;
    },
  });

  if (!task.active_execution_run_id) {
    return <EmptyState title="No verification run" detail="Verification has not started for this task." />;
  }

  if (query.isLoading) {
    return <LoadingState title="Loading verification" rows={5} />;
  }

  if (query.isError) {
    return <ErrorState error={query.error} onRetry={() => query.refetch()} />;
  }

  const run = query.data;
  if (!run) {
    return <EmptyState title="No verification run" />;
  }

  return (
    <div className="mx-auto flex max-w-5xl flex-col gap-4">
      <div className="flex items-center justify-between border-b border-[#30363D] pb-3">
        <h2 className="flex items-center gap-2 text-base font-bold text-[#dae3ee]">
          <Terminal className="h-5 w-5 text-[#acc7ff]" />
          Automated Verification
        </h2>
        <StatusBadge status={run.timed_out ? "timeout" : run.status} />
      </div>

      <div className="grid grid-cols-1 gap-3 md:grid-cols-4">
        {Object.entries(run.checks).length > 0 ? (
          Object.entries(run.checks).map(([name, status]) => (
            <div key={name} className="rounded-lg border border-[#30363D] bg-[#141c24] p-3">
              <div className="font-code text-[11px] uppercase tracking-wider text-zinc-500">{name}</div>
              <div className="mt-2">
                <StatusBadge status={status.toLowerCase()} />
              </div>
            </div>
          ))
        ) : (
          <div className="rounded-lg border border-[#30363D] bg-[#141c24] p-3 text-xs text-zinc-400">
            No check breakdown provided.
          </div>
        )}
      </div>

      <section className="rounded-lg border border-[#30363D] bg-[#141c24]">
        <div className="flex items-center justify-between border-b border-[#30363D] px-4 py-3">
          <h3 className="text-sm font-bold text-[#dae3ee]">Execution Logs</h3>
          <span className="font-code text-xs text-zinc-500">
            {run.duration_ms ? `${Math.round(run.duration_ms)}ms` : "—"}
          </span>
        </div>
        <div className="max-h-[56vh] overflow-auto bg-black p-4 font-code text-xs leading-relaxed text-[#dae3ee]">
          {run.results.length > 0 ? (
            run.results.map((result) => (
              <div key={`${result.name}-${result.command_type}`} className="mb-5 last:mb-0">
                <div className="mb-2 flex flex-wrap items-center gap-2">
                  <span className="font-semibold text-[#acc7ff]">{result.name}</span>
                  <StatusBadge status={result.status.toLowerCase()} />
                  <span className="text-zinc-500">exit {result.exit_code ?? "—"}</span>
                  <span className="text-zinc-500">{formatMs(result.duration_ms)}</span>
                  <CopyButton value={`${result.stdout}\n${result.stderr}`} label="Logs" />
                </div>
                {result.stdout ? (
                  <pre className="mb-2 overflow-x-auto whitespace-pre text-[#dae3ee]">{result.stdout}</pre>
                ) : null}
                {result.stderr ? (
                  <pre className="overflow-x-auto whitespace-pre text-[#ff7b72]">{result.stderr}</pre>
                ) : null}
                {result.stdout_truncated || result.stderr_truncated ? (
                  <div className="mt-2 text-amber-300">Log output was truncated by the backend.</div>
                ) : null}
              </div>
            ))
          ) : (
            <div className="text-zinc-500">No command logs returned.</div>
          )}
          {run.error_message ? (
            <div className="mt-4 rounded border border-rose-500/30 bg-rose-500/10 p-3 text-rose-100">
              {run.error_message}
            </div>
          ) : null}
        </div>
      </section>
    </div>
  );
}

/** Purpose: Format ms for this frontend workflow. */
function formatMs(value: number | null | undefined) {
  return typeof value === "number" && Number.isFinite(value) ? `${Math.round(value)}ms` : "—";
}
