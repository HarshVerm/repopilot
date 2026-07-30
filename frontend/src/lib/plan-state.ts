// Module purpose: Centralize plan-review eligibility rules used by the UI.

import type { PlanResponse, TaskStatus } from "@/types/api";

/** Purpose: Report whether the planner stopped because it needs user input. */
export function planNeedsClarification(plan: PlanResponse) {
  return plan.plan.needs_more_context;
}

/** Purpose: Prevent approval unless both task and plan are ready for it. */
export function canApprovePlan(
  taskStatus: TaskStatus,
  plan: PlanResponse,
) {
  return (
    taskStatus === "plan_pending_approval" &&
    plan.status === "pending_approval" &&
    !planNeedsClarification(plan)
  );
}
