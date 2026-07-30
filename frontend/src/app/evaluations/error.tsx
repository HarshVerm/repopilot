"use client";

// Module purpose: Render and recover from errors for this application route.

import { ErrorState } from "@/components/shared/error-state";

/** Purpose: Render the evaluations error interface. */
export default function EvaluationsError({ error, reset }: { error: Error; reset: () => void }) {
  return (
    <div className="p-6">
      <ErrorState error={error} onRetry={reset} />
    </div>
  );
}
