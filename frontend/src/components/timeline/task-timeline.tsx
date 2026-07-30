"use client";

// Module purpose: Render and coordinate the task timeline interface.

import { useQuery } from "@tanstack/react-query";
import { Clock } from "lucide-react";
import type { TaskResponse } from "@/types/api";
import { getTaskTimeline } from "@/lib/api/tasks";
import { formatDateTime, formatStatus } from "@/lib/formatters";
import { queryKeys } from "@/lib/query-client";
import { EmptyState } from "@/components/shared/empty-state";
import { ErrorState } from "@/components/shared/error-state";
import { LoadingState } from "@/components/shared/loading-state";

/** Purpose: Render the task timeline interface. */
export function TaskTimeline({ task }: { task: TaskResponse }) {
  const query = useQuery({
    queryKey: queryKeys.taskTimeline(task.task_id),
    queryFn: ({ signal }) => getTaskTimeline(task.task_id, signal),
    refetchInterval: task.status === "completed" || task.status === "failed" || task.status === "cancelled" ? false : 5000,
  });

  if (query.isLoading) return <LoadingState title="Loading timeline" rows={5} />;
  if (query.isError) return <ErrorState error={query.error} onRetry={() => query.refetch()} />;

  const events = query.data?.events ?? [];
  if (events.length === 0) {
    return <EmptyState title="No timeline events" />;
  }

  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-4">
      <h2 className="flex items-center gap-2 border-b border-[#30363D] pb-3 text-base font-bold text-[#dae3ee]">
        <Clock className="h-5 w-5 text-[#acc7ff]" />
        Agent Workflow Timeline
      </h2>
      <div className="relative ml-4 space-y-6 border-l-2 border-[#30363D] pl-6">
        {events.map((event) => (
          <article key={event.event_id} className="relative">
            <div className="absolute -left-[31px] top-0 h-3 w-3 rounded-full border-2 border-[#0D1117] bg-[#acc7ff]" />
            <div className="flex items-start justify-between gap-4">
              <h3 className="text-xs font-bold text-[#dae3ee]">{formatStatus(event.event_type.replace(/\./g, "_"))}</h3>
              <span className="shrink-0 font-code text-[11px] text-[#8b909f]">
                {formatDateTime(event.created_at)}
              </span>
            </div>
            <p className="mt-1 text-xs text-[#c1c6d6]">{timelineMessage(event)}</p>
            {Object.keys(event.metadata).length > 0 ? (
              <details className="mt-2">
                <summary className="cursor-pointer text-[11px] text-zinc-500">Metadata</summary>
                <pre className="mt-2 overflow-x-auto rounded border border-[#30363D] bg-black p-3 font-code text-[11px] text-zinc-300">
                  {JSON.stringify(event.metadata, null, 2)}
                </pre>
              </details>
            ) : null}
          </article>
        ))}
      </div>
    </div>
  );
}

/** Purpose: Handle timeline message for this frontend module. */
function timelineMessage(event: {
  message: string | null;
  status: string | null;
  metadata: Record<string, unknown>;
}) {
  if (event.message) return event.message;
  if (event.status) return event.status;
  if (typeof event.metadata.repository === "string") return event.metadata.repository;
  return "Event recorded";
}
