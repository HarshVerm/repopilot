// Module purpose: Render the loading state for this application route.

import { LoadingState } from "@/components/shared/loading-state";

/** Purpose: Render the tasks loading interface. */
export default function TasksLoading() {
  return (
    <div className="p-6">
      <LoadingState title="Loading tasks" rows={8} />
    </div>
  );
}
