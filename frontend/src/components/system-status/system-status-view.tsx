"use client";

// Module purpose: Render and coordinate the system status view interface.

import { useQuery } from "@tanstack/react-query";
import { Database, Server } from "lucide-react";
import type { ReactNode } from "react";
import { PageHeader } from "@/components/app-shell/page-header";
import { ErrorState } from "@/components/shared/error-state";
import { LoadingState } from "@/components/shared/loading-state";
import { StatusBadge } from "@/components/shared/status-badge";
import { getHealth, getReadiness } from "@/lib/api/health";
import { queryKeys } from "@/lib/query-client";

/** Purpose: Render the system status view interface. */
export function SystemStatusView() {
  const health = useQuery({
    queryKey: queryKeys.health,
    queryFn: ({ signal }) => getHealth(signal),
    refetchInterval: 15000,
  });
  const readiness = useQuery({
    queryKey: queryKeys.readiness,
    queryFn: ({ signal }) => getReadiness(signal),
    refetchInterval: 15000,
    retry: false,
  });

  return (
    <>
      <PageHeader title="System Status" subtitle="FastAPI health and readiness checks" />
      <div className="flex-1 space-y-6 overflow-y-auto p-6">
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          <StatusCard
            icon={<Server className="h-8 w-8 text-[#acc7ff]" />}
            label="API"
            status={health.data?.status ?? (health.isError ? "unavailable" : "loading")}
            detail="/health"
          />
          <StatusCard
            icon={<Database className="h-8 w-8 text-emerald-400" />}
            label="Readiness"
            status={readiness.data?.status ?? (readiness.isError ? "not_ready" : "loading")}
            detail="/ready"
          />
        </div>

        {health.isError ? <ErrorState error={health.error} onRetry={() => health.refetch()} /> : null}
        {readiness.isLoading ? <LoadingState title="Loading readiness" rows={4} /> : null}
        {readiness.isError ? <ErrorState error={readiness.error} onRetry={() => readiness.refetch()} /> : null}

        {readiness.data ? (
          <section className="rounded-lg border border-[#30363D] bg-[#161B22]">
            <div className="border-b border-[#30363D] p-4">
              <h2 className="text-sm font-bold text-[#dae3ee]">Readiness Checks</h2>
            </div>
            <div className="divide-y divide-[#30363D] bg-[#0D1117]">
              {Object.entries(readiness.data.checks).map(([name, check]) => (
                <div key={name} className="flex items-center justify-between gap-4 p-4 text-xs">
                  <div className="min-w-0">
                    <div className="font-code font-semibold text-[#dae3ee]">{name}</div>
                    <div className="mt-1 text-zinc-500">{check.details ?? "No details reported"}</div>
                  </div>
                  <StatusBadge status={check.status} />
                </div>
              ))}
            </div>
          </section>
        ) : null}
      </div>
    </>
  );
}

/** Purpose: Render the status card interface. */
function StatusCard({
  icon,
  label,
  status,
  detail,
}: {
  icon: ReactNode;
  label: string;
  status: string;
  detail: string;
}) {
  return (
    <div className="flex items-center justify-between rounded-lg border border-[#30363D] bg-[#161B22] p-4">
      <div>
        <span className="text-[11px] font-semibold uppercase tracking-wider text-[#c1c6d6]">{label}</span>
        <div className="mt-2">
          <StatusBadge status={status} />
        </div>
        <span className="mt-2 block text-[11px] text-[#8b909f]">{detail}</span>
      </div>
      {icon}
    </div>
  );
}
