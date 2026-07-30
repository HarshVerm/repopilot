"use client";

// Module purpose: Render and recover from errors for this application route.

import { ErrorState } from "@/components/shared/error-state";

/** Purpose: Render the settings error interface. */
export default function SettingsError({ error, reset }: { error: Error; reset: () => void }) {
  return (
    <div className="p-6">
      <ErrorState error={error} onRetry={reset} />
    </div>
  );
}
