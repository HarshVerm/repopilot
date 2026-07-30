"use client";

// Module purpose: Render and recover from errors for this application route.

import { ErrorState } from "@/components/shared/error-state";

/** Purpose: Render the git hub error interface. */
export default function GitHubError({ error, reset }: { error: Error; reset: () => void }) {
  return (
    <div className="p-6">
      <ErrorState error={error} onRetry={reset} />
    </div>
  );
}
