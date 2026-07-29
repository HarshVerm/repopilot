import type { PublicationResponse, TaskResponse } from "@/types/api";
import type { TaskAction } from "@/types/task";
import { isCancellableStatus } from "./task-status";

export function canRetryPublication(
  task: TaskResponse,
  publication?: PublicationResponse | null,
) {
  if (!task.active_review_id || !publication) {
    return false;
  }

  return (
    (task.status === "failed" && publication.status === "failed") ||
    (task.status === "publishing" && publication.status === "partially_published")
  );
}

export function getAvailableTaskActions(
  task: TaskResponse,
  publication?: PublicationResponse | null,
): TaskAction[] {
  const actions: TaskAction[] = [];

  if (task.status === "plan_pending_approval" && task.active_plan_id) {
    actions.push({ id: "review_plan", label: "Review Plan", kind: "primary" });
  }

  if (task.status === "review_pending" && task.active_review_id) {
    actions.push({
      id: "review_final_diff",
      label: "Review Final Diff",
      kind: "primary",
    });
  }

  if (task.status === "review_approved" && task.active_review_id) {
    actions.push({
      id: "publish_pull_request",
      label: "Publish Pull Request",
      kind: "primary",
      disabled: Boolean(publication && publication.status === "publishing"),
    });
  } else if (canRetryPublication(task, publication)) {
    actions.push({
      id: "publish_pull_request",
      label: "Retry Publishing",
      kind: "primary",
    });
  }

  if (task.status === "completed" && publication?.pull_request_url) {
    actions.push({
      id: "open_pull_request",
      label: "Open Pull Request",
      kind: "link",
    });
  }

  if (isCancellableStatus(task.status)) {
    actions.push({ id: "cancel_task", label: "Cancel Task", kind: "danger" });
  }

  return actions;
}
