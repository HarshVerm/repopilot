"use client";

import { useQuery } from "@tanstack/react-query";
import { Shield, Timer, Zap } from "lucide-react";
import type { ReactNode } from "react";
import type { TaskResponse } from "@/types/api";
import { getTaskMetrics } from "@/lib/api/tasks";
import { formatNumber, metricValue } from "@/lib/formatters";
import { queryKeys } from "@/lib/query-client";
import { EmptyState } from "@/components/shared/empty-state";
import { ErrorState } from "@/components/shared/error-state";
import { LoadingState } from "@/components/shared/loading-state";

export function TaskMetrics({ task }: { task: TaskResponse }) {
  const query = useQuery({
    queryKey: queryKeys.taskMetrics(task.task_id),
    queryFn: ({ signal }) => getTaskMetrics(task.task_id, signal),
  });

  if (query.isLoading) return <LoadingState title="Loading metrics" rows={5} />;
  if (query.isError) return <ErrorState error={query.error} onRetry={() => query.refetch()} />;

  const metrics = query.data?.metrics;
  if (!metrics || Object.keys(metrics).length === 0) {
    return <EmptyState title="No metrics yet" />;
  }

  return (
    <div className="mx-auto grid max-w-5xl grid-cols-1 gap-4 md:grid-cols-3">
      <MetricCard
        icon={<Zap className="h-4 w-4 text-[#acc7ff]" />}
        label="Total Tokens"
        value={formatNumber(metricValue(metrics, ["agents", "total", "total_tokens"]))}
        detail={`Planner ${formatNumber(metricValue(metrics, ["agents", "planner", "total_tokens"]))}`}
      />
      <MetricCard
        icon={<Timer className="h-4 w-4 text-[#acc7ff]" />}
        label="Total Duration"
        value={formatMs(metricValue(metrics, ["agents", "total", "latency_ms"]))}
        detail={`Sandbox ${formatNumber(metricValue(metrics, ["sandbox", "runs"]))} runs`}
      />
      <MetricCard
        icon={<Shield className="h-4 w-4 text-[#acc7ff]" />}
        label="Debug Attempts"
        value={formatNumber(metricValue(metrics, ["debugging", "attempts"]))}
        detail={`Files changed ${formatNumber(metricValue(metrics, ["changes", "files_changed"]))}`}
      />
      <pre className="md:col-span-3 overflow-x-auto rounded-lg border border-[#30363D] bg-black p-4 font-code text-xs text-zinc-300">
        {JSON.stringify(metrics, null, 2)}
      </pre>
    </div>
  );
}

function formatMs(value: unknown) {
  return typeof value === "number" && Number.isFinite(value) ? `${Math.round(value)}ms` : "—";
}

function MetricCard({
  icon,
  label,
  value,
  detail,
}: {
  icon: ReactNode;
  label: string;
  value: string;
  detail: string;
}) {
  return (
    <div className="flex flex-col gap-2 rounded-lg border border-[#30363D] bg-[#141c24] p-4">
      <span className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-[#c1c6d6]">
        {icon}
        {label}
      </span>
      <div className="font-code text-2xl font-bold text-[#dae3ee]">{value}</div>
      <div className="text-xs text-[#8b909f]">{detail}</div>
    </div>
  );
}
