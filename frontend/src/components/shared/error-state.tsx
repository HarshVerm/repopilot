// Module purpose: Render and coordinate the error state interface.

import { AlertTriangle, RefreshCw } from "lucide-react";
import { errorMessage, errorTitle } from "@/lib/errors";

/** Purpose: Render the error state interface. */
export function ErrorState({
  error,
  onRetry,
}: {
  error: unknown;
  onRetry?: () => void;
}) {
  return (
    <div className="rounded-xl border border-rose-500/30 bg-rose-500/10 p-4">
      <div className="flex items-start gap-3">
        <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-rose-400" />
        <div className="min-w-0 flex-1">
          <h2 className="text-sm font-semibold text-rose-300">{errorTitle(error)}</h2>
          <p className="mt-1 text-xs leading-relaxed text-rose-100/80">{errorMessage(error)}</p>
        </div>
        {onRetry ? (
          <button
            type="button"
            onClick={onRetry}
            className="inline-flex shrink-0 items-center gap-2 rounded-lg border border-rose-500/30 bg-rose-950/30 px-3 py-1.5 text-xs font-semibold text-rose-100 hover:bg-rose-900/40"
          >
            <RefreshCw className="h-3.5 w-3.5" />
            Retry
          </button>
        ) : null}
      </div>
    </div>
  );
}
