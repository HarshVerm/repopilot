// Module purpose: Render and coordinate the status badge interface.

import { AlertCircle, CheckCircle2, Clock, Loader2, MinusCircle } from "lucide-react";
import { formatStatus } from "@/lib/formatters";
import { taskStatusTone } from "@/lib/task-status";

const toneClass = {
  success: "border-emerald-500/25 bg-emerald-500/10 text-emerald-400",
  active: "border-blue-500/25 bg-blue-500/10 text-blue-400",
  attention: "border-amber-500/25 bg-amber-500/10 text-amber-400",
  error: "border-rose-500/25 bg-rose-500/10 text-rose-400",
  neutral: "border-zinc-700 bg-zinc-800/70 text-zinc-300",
};

/** Purpose: Render the status icon interface. */
function StatusIcon({ tone }: { tone: keyof typeof toneClass }) {
  if (tone === "success") return <CheckCircle2 className="h-3.5 w-3.5" />;
  if (tone === "active") return <Loader2 className="h-3.5 w-3.5 animate-spin" />;
  if (tone === "attention") return <Clock className="h-3.5 w-3.5" />;
  if (tone === "error") return <AlertCircle className="h-3.5 w-3.5" />;
  return <MinusCircle className="h-3.5 w-3.5" />;
}

/** Purpose: Render the status badge interface. */
export function StatusBadge({
  status,
  label,
  className = "",
}: {
  status: string;
  label?: string;
  className?: string;
}) {
  const tone = taskStatusTone(status);

  return (
    <span
      className={`inline-flex max-w-full items-center gap-1.5 rounded-full border px-2.5 py-1 text-[10px] font-semibold uppercase tracking-wider ${toneClass[tone]} ${className}`}
    >
      <StatusIcon tone={tone} />
      <span className="truncate">{label ?? formatStatus(status)}</span>
    </span>
  );
}
