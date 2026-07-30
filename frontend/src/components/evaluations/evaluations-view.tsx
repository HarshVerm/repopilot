"use client";

// Module purpose: Render and coordinate the evaluations view interface.

import { useMutation } from "@tanstack/react-query";
import { Award, Play } from "lucide-react";
import { useState } from "react";
import { PageHeader } from "@/components/app-shell/page-header";
import { EmptyState } from "@/components/shared/empty-state";
import { ErrorState } from "@/components/shared/error-state";
import { runEvaluation } from "@/lib/api/evaluations";

/** Purpose: Render the evaluations view interface. */
export function EvaluationsView() {
  const [suite, setSuite] = useState("");
  const [maxTasks, setMaxTasks] = useState("");
  const [live, setLive] = useState(false);
  const mutation = useMutation({
    mutationFn: () =>
      runEvaluation({
        suite: suite.trim() || undefined,
        max_tasks: maxTasks.trim() ? Number(maxTasks) : undefined,
        dry_run: !live,
        live,
      }),
  });

  return (
    <>
      <PageHeader title="Evaluations" subtitle="Backend evaluation API" />
      <div className="flex-1 space-y-6 overflow-y-auto p-6">
        <div>
          <h1 className="flex items-center gap-2 text-xl font-bold text-[#dae3ee]">
            <Award className="h-5 w-5 text-[#acc7ff]" />
            Evaluations
          </h1>
          <p className="mt-1 text-xs text-[#c1c6d6]">
            Results are displayed only after the FastAPI evaluation API returns them.
          </p>
        </div>

        <section className="rounded-lg border border-[#30363D] bg-[#161B22] p-5">
          <div className="grid grid-cols-1 gap-4 md:grid-cols-[1fr_160px_auto]">
            <label className="flex flex-col gap-1.5">
              <span className="text-[11px] font-semibold uppercase tracking-widest text-zinc-400">
                Suite
              </span>
              <input
                value={suite}
                onChange={(event) => setSuite(event.target.value)}
                placeholder="Backend default"
                className="rounded-lg border border-[#3F3F46] bg-[#0D1117] px-3 py-2 font-code text-xs text-[#FAFAFA]"
              />
            </label>
            <label className="flex flex-col gap-1.5">
              <span className="text-[11px] font-semibold uppercase tracking-widest text-zinc-400">
                Max Tasks
              </span>
              <input
                value={maxTasks}
                onChange={(event) => setMaxTasks(event.target.value.replace(/\D/g, ""))}
                placeholder="Backend default"
                className="rounded-lg border border-[#3F3F46] bg-[#0D1117] px-3 py-2 font-code text-xs text-[#FAFAFA]"
              />
            </label>
            <label className="flex items-end gap-2 pb-2 text-xs text-zinc-300">
              <input
                type="checkbox"
                checked={live}
                onChange={(event) => setLive(event.target.checked)}
                className="h-4 w-4 accent-blue-600"
              />
              Live run
            </label>
          </div>

          <div className="mt-4 flex items-center justify-between gap-4 border-t border-[#30363D] pt-4">
            <p className="text-xs text-[#8b909f]">
              Live runs require backend `EVALUATION_MODE=true`; dry runs use the same backend endpoint.
            </p>
            <button
              type="button"
              onClick={() => mutation.mutate()}
              disabled={mutation.isPending}
              className="inline-flex items-center gap-2 rounded-lg bg-blue-600 px-4 py-2 text-xs font-semibold text-white hover:bg-blue-500 disabled:opacity-50"
            >
              <Play className="h-3.5 w-3.5" />
              {mutation.isPending ? "Running..." : live ? "Run Live Evaluation" : "Run Dry Evaluation"}
            </button>
          </div>
        </section>

        {mutation.isIdle ? (
          <EmptyState
            title="No evaluation result"
            detail="Run an evaluation to load real backend output."
          />
        ) : null}

        {mutation.isError ? <ErrorState error={mutation.error} /> : null}

        {mutation.data ? (
          <section className="rounded-lg border border-[#30363D] bg-[#161B22]">
            <div className="border-b border-[#30363D] p-4">
              <h2 className="text-sm font-bold text-[#dae3ee]">Evaluation Run</h2>
              <p className="mt-1 font-code text-xs text-[#8b909f]">{mutation.data.run_id}</p>
            </div>
            <pre className="max-h-[60vh] overflow-auto bg-black p-4 font-code text-xs text-zinc-300">
              {JSON.stringify(mutation.data.report, null, 2)}
            </pre>
          </section>
        ) : null}
      </div>
    </>
  );
}
