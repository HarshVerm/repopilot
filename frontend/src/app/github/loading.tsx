import { LoadingState } from "@/components/shared/loading-state";

export default function GitHubLoading() {
  return (
    <div className="p-6">
      <LoadingState title="Loading GitHub data" rows={5} />
    </div>
  );
}
