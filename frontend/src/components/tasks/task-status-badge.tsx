import type { TaskStatus } from "@/types/api";
import { StatusBadge } from "@/components/shared/status-badge";

export function TaskStatusBadge({ status }: { status: TaskStatus }) {
  const label =
    status === "plan_pending_approval" || status === "review_pending"
      ? "Needs Review"
      : status === "review_approved"
        ? "Diff Approved"
        : undefined;

  return <StatusBadge status={status} label={label} />;
}
