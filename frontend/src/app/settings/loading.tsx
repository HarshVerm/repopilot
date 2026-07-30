// Module purpose: Render the loading state for this application route.

import { LoadingState } from "@/components/shared/loading-state";

/** Purpose: Render the settings loading interface. */
export default function SettingsLoading() {
  return (
    <div className="p-6">
      <LoadingState title="Loading settings" rows={3} />
    </div>
  );
}
