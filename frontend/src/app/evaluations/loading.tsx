// Module purpose: Render the loading state for this application route.

import { LoadingState } from "@/components/shared/loading-state";

/** Purpose: Render the evaluations loading interface. */
export default function EvaluationsLoading() {
  return (
    <div className="p-6">
      <LoadingState title="Loading evaluations" rows={5} />
    </div>
  );
}
