"use client";

import { useQuery } from "@tanstack/react-query";
import { getHealth } from "@/lib/api/health";
import { queryKeys } from "@/lib/query-client";

export function Footer() {
  const health = useQuery({
    queryKey: queryKeys.health,
    queryFn: ({ signal }) => getHealth(signal),
    refetchInterval: 15000,
  });
  const healthy = health.data?.status === "healthy";

  return (
    <footer className="fixed bottom-0 right-0 left-16 z-30 flex h-8 shrink-0 items-center justify-between border-t border-[#27272A] bg-[#09090B] px-6 py-1 text-[10px] font-semibold uppercase tracking-[0.15em] text-zinc-500 lg:left-64">
      <div className="flex items-center gap-2">
        <span
          className={`h-2 w-2 rounded-full ${
            healthy
              ? "bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.5)]"
              : "bg-rose-500 shadow-[0_0_8px_rgba(244,63,94,0.5)]"
          }`}
        />
        <span className="text-zinc-400">RepoPilot API {healthy ? "healthy" : "unavailable"}</span>
      </div>
      <div className="hidden items-center gap-6 text-[10px] tracking-widest text-zinc-500 sm:flex">
        <span>FastAPI</span>
        <span>Next.js</span>
        <span>Human Gates Enforced</span>
      </div>
    </footer>
  );
}
