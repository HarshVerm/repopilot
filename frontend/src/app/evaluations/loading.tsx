import { LoadingState } from "@/components/shared/loading-state";

export default function EvaluationsLoading() {
  return (
    <div className="p-6">
      <LoadingState title="Loading evaluations" rows={5} />
    </div>
  );
}
