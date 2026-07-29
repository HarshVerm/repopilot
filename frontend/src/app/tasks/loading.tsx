import { LoadingState } from "@/components/shared/loading-state";

export default function TasksLoading() {
  return (
    <div className="p-6">
      <LoadingState title="Loading tasks" rows={8} />
    </div>
  );
}
