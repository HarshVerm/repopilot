import { LoadingState } from "@/components/shared/loading-state";

export default function SystemStatusLoading() {
  return (
    <div className="p-6">
      <LoadingState title="Loading system status" rows={5} />
    </div>
  );
}
