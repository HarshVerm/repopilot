// Module purpose: Render and coordinate the task lifecycle interface.

import { AlertTriangle, Check, Clock, Loader2, Minus } from "lucide-react";
import type { TaskResponse } from "@/types/api";
import { getTaskLifecycle } from "@/lib/task-status";

/** Purpose: Render the stage icon interface. */
function StageIcon({ state, index }: { state: string; index: number }) {
  if (state === "completed") return <Check className="h-3.5 w-3.5 stroke-[3]" />;
  if (state === "active") return <Loader2 className="h-3.5 w-3.5 animate-spin" />;
  if (state === "waiting") return <Clock className="h-3.5 w-3.5" />;
  if (state === "failed") return <AlertTriangle className="h-3.5 w-3.5" />;
  if (state === "skipped") return <Minus className="h-3.5 w-3.5" />;
  return <span className="font-code text-[10px]">{index + 1}</span>;
}

/** Purpose: Render the task lifecycle interface. */
export function TaskLifecycle({ task }: { task: TaskResponse }) {
  const stages = getTaskLifecycle(task);

  return (
    <div className="mt-1 flex items-center gap-2 overflow-x-auto rounded-2xl border border-[#27272A] bg-[#09090B] px-4 py-3">
      {stages.map((stage, index) => {
        const color =
          stage.state === "completed"
            ? "bg-zinc-200 text-zinc-900"
            : stage.state === "active"
              ? "border-blue-500 text-blue-400"
              : stage.state === "waiting"
                ? "border-amber-500 text-amber-400"
                : stage.state === "failed"
                  ? "border-rose-500 text-rose-400"
                  : stage.state === "skipped"
                    ? "border-zinc-600 text-zinc-500"
                    : "border-zinc-700 text-zinc-500";

        return (
          <div key={stage.id} className="flex min-w-fit items-center gap-2">
            <div className={`flex flex-col items-center gap-1 px-1 ${stage.state === "upcoming" ? "opacity-55" : ""}`}>
              <div className={`flex h-6 w-6 items-center justify-center rounded-full border text-xs transition-colors ${color}`}>
                <StageIcon state={stage.state} index={index} />
              </div>
              <span
                className={`whitespace-nowrap font-code text-[10px] ${
                  stage.state === "active"
                    ? "font-bold text-blue-400"
                    : stage.state === "waiting"
                      ? "font-bold text-amber-400"
                      : stage.state === "failed"
                        ? "font-bold text-rose-400"
                        : stage.state === "completed"
                          ? "text-zinc-300"
                          : "text-zinc-500"
                }`}
              >
                {stage.label}
              </span>
            </div>
            {index < stages.length - 1 ? (
              <div
                className={`h-px w-8 shrink-0 ${
                  stage.state === "completed" ? "bg-zinc-400" : "bg-[#27272A]"
                }`}
              />
            ) : null}
          </div>
        );
      })}
    </div>
  );
}
