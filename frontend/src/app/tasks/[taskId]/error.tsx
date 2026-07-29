"use client";

import { ErrorState } from "@/components/shared/error-state";

export default function TaskDetailError({ error, reset }: { error: Error; reset: () => void }) {
  return (
    <div className="p-6">
      <ErrorState error={error} onRetry={reset} />
    </div>
  );
}
