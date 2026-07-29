import { LoadingState } from "@/components/shared/loading-state";

export default function TaskDetailLoading() {
  return (
    <div className="p-6">
      <LoadingState title="Loading task" rows={8} />
    </div>
  );
}
