import type { TaskResponse, TaskStatus } from "@/types/api";
import type { LifecycleStage, LifecycleStageId, LifecycleStageState } from "@/types/task";
import {
  ACTIVE_TASK_STATUSES,
  TERMINAL_TASK_STATUSES,
  WAITING_TASK_STATUSES,
} from "@/types/task";

export const LIFECYCLE_STAGES: Array<{ id: LifecycleStageId; label: string }> = [
  { id: "repository", label: "Repository" },
  { id: "index", label: "Index" },
  { id: "retrieval", label: "Retrieval" },
  { id: "planning", label: "Planning" },
  { id: "plan_approval", label: "Plan Approval" },
  { id: "coding", label: "Coding" },
  { id: "verification", label: "Verification" },
  { id: "debugger", label: "Debugger" },
  { id: "final_review", label: "Final Review" },
  { id: "publishing", label: "Publishing" },
];

const lifecycleIndexByStatus: Record<TaskStatus, number> = {
  created: 0,
  repository_preparing: 0,
  repository_ready: 0,
  indexing: 1,
  indexed: 1,
  retrieving: 2,
  planning: 3,
  plan_pending_approval: 4,
  plan_approved: 4,
  plan_rejected: 4,
  plan_revision_required: 3,
  coding: 5,
  patch_generated: 5,
  testing: 6,
  test_failed: 6,
  debugging: 7,
  verification_passed: 6,
  review_pending: 8,
  review_approved: 8,
  review_rejected: 8,
  publishing: 9,
  completed: 9,
  failed: 9,
  cancelled: 9,
};

const lifecycleIndexByFailureCategory: Record<string, number> = {
  github_error: 0,
  repository_clone_error: 0,
  indexing_error: 1,
  retrieval_error: 2,
  planner_error: 3,
  planner_validation_error: 3,
  plan_revision_required: 3,
  coder_error: 5,
  patch_policy_error: 5,
  test_failure: 6,
  typecheck_failure: 6,
  lint_failure: 6,
  build_failure: 6,
  dependency_failure: 6,
  sandbox_error: 6,
  sandbox_timeout: 6,
  debugger_error: 7,
  debug_attempts_exhausted: 7,
  debug_no_progress: 7,
  review_integrity_error: 8,
  review_rejected: 8,
  git_error: 9,
  github_publish_error: 9,
};

const waitingStatuses = new Set<TaskStatus>(WAITING_TASK_STATUSES);
const activeStatuses = new Set<TaskStatus>(ACTIVE_TASK_STATUSES);
const terminalStatuses = new Set<TaskStatus>(TERMINAL_TASK_STATUSES);

export function isActiveTask(task: Pick<TaskResponse, "status">) {
  return activeStatuses.has(task.status);
}

export function isTerminalTask(task: Pick<TaskResponse, "status">) {
  return terminalStatuses.has(task.status);
}

export function isWaitingForHuman(task: Pick<TaskResponse, "status">) {
  return waitingStatuses.has(task.status);
}

export function isCancellableStatus(status: TaskStatus) {
  return !terminalStatuses.has(status) && status !== "publishing";
}

export function isRestartableStatus(status: TaskStatus) {
  return (
    status === "failed" ||
    status === "cancelled" ||
    status === "plan_revision_required"
  );
}

export function taskStatusTone(status: string): "success" | "active" | "attention" | "error" | "neutral" {
  if (status === "completed" || status === "approved" || status === "published" || status === "passed") {
    return "success";
  }

  if (status === "failed" || status === "rejected" || status === "review_rejected" || status === "plan_rejected" || status === "plan_revision_required" || status === "error" || status === "timeout") {
    return "error";
  }

  if (status.includes("pending") || status.includes("review") || status.includes("approval") || status === "test_failed") {
    return "attention";
  }

  if (status === "running" || status === "publishing" || status === "coding" || status === "debugging" || status === "testing" || status === "planning") {
    return "active";
  }

  return "neutral";
}

export function getTaskLifecycle(
  task: Pick<TaskResponse, "status" | "failure_category" | "current_step">,
): LifecycleStage[] {
  const persistedStageIndex = Math.min(
    LIFECYCLE_STAGES.length - 1,
    Math.max(0, task.current_step - 1),
  );
  let activeIndex = lifecycleIndexByStatus[task.status] ?? 0;

  if (task.status === "failed" && task.failure_category) {
    activeIndex =
      lifecycleIndexByFailureCategory[task.failure_category] ??
      persistedStageIndex;
  } else if (task.status === "failed" || task.status === "cancelled") {
    activeIndex = persistedStageIndex;
  }

  return LIFECYCLE_STAGES.map((stage, index) => {
    let state: LifecycleStageState = "upcoming";

    if (task.status === "failed") {
      state = index < activeIndex ? "completed" : index === activeIndex ? "failed" : "upcoming";
    } else if (task.status === "cancelled") {
      state = index < activeIndex ? "completed" : index === activeIndex ? "skipped" : "upcoming";
    } else if (
      task.status === "plan_rejected" ||
      task.status === "plan_revision_required" ||
      task.status === "review_rejected"
    ) {
      state = index < activeIndex ? "completed" : index === activeIndex ? "failed" : "upcoming";
    } else if (task.status === "completed") {
      state = "completed";
    } else if (index < activeIndex) {
      state = "completed";
    } else if (index === activeIndex) {
      state = waitingStatuses.has(task.status) ? "waiting" : "active";
    }

    return {
      ...stage,
      state,
    };
  });
}
