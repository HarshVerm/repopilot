// Module purpose: Render the loading state for this application route.

import { LoadingState } from "@/components/shared/loading-state";

/** Purpose: Render the system status loading interface. */
export default function SystemStatusLoading() {
  return (
    <div className="p-6">
      <LoadingState title="Loading system status" rows={5} />
    </div>
  );
}
