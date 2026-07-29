import type { TaskStatus } from "./api";

export type TaskTab =
  | "overview"
  | "plan"
  | "changes"
  | "verification"
  | "debug"
  | "timeline"
  | "metrics";

export type LifecycleStageId =
  | "repository"
  | "index"
  | "retrieval"
  | "planning"
  | "plan_approval"
  | "coding"
  | "verification"
  | "debugger"
  | "final_review"
  | "publishing";

export type LifecycleStageState =
  | "completed"
  | "active"
  | "waiting"
  | "failed"
  | "skipped"
  | "upcoming";

export interface LifecycleStage {
  id: LifecycleStageId;
  label: string;
  state: LifecycleStageState;
}

export type TaskActionId =
  | "review_plan"
  | "cancel_task"
  | "review_final_diff"
  | "publish_pull_request"
  | "open_pull_request";

export interface TaskAction {
  id: TaskActionId;
  label: string;
  kind: "primary" | "secondary" | "danger" | "link";
  disabled?: boolean;
}

export const ACTIVE_TASK_STATUSES: TaskStatus[] = [
  "created",
  "repository_preparing",
  "indexing",
  "retrieving",
  "planning",
  "plan_approved",
  "coding",
  "patch_generated",
  "testing",
  "test_failed",
  "debugging",
  "verification_passed",
  "publishing",
];

export const TERMINAL_TASK_STATUSES: TaskStatus[] = [
  "plan_rejected",
  "review_rejected",
  "completed",
  "failed",
  "cancelled",
];

export const WAITING_TASK_STATUSES: TaskStatus[] = [
  "plan_pending_approval",
  "plan_revision_required",
  "review_pending",
  "review_approved",
];
