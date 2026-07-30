// Module purpose: Render the loading state for this application route.

import { LoadingState } from "@/components/shared/loading-state";

/** Purpose: Render the task detail loading interface. */
export default function TaskDetailLoading() {
  return (
    <div className="p-6">
      <LoadingState title="Loading task" rows={8} />
    </div>
  );
}
