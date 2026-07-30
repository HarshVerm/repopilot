// Module purpose: Render the loading state for this application route.

import { LoadingState } from "@/components/shared/loading-state";

/** Purpose: Render the git hub loading interface. */
export default function GitHubLoading() {
  return (
    <div className="p-6">
      <LoadingState title="Loading GitHub data" rows={5} />
    </div>
  );
}
