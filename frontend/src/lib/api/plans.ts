// Module purpose: Provide typed API operations for plans.

import type { PlanResponse, PlanStatusResponse } from "@/types/api";
import { apiRequest } from "./client";

/** Purpose: Return plan for this frontend workflow. */
export function getPlan(planId: string, signal?: AbortSignal) {
  return apiRequest<PlanResponse>(`/api/v1/plans/${planId}`, { signal });
}

/** Purpose: Approve plan for this frontend workflow. */
export function approvePlan(planId: string) {
  return apiRequest<PlanStatusResponse>(`/api/v1/plans/${planId}/approve`, {
    method: "POST",
  });
}

/** Purpose: Reject plan for this frontend workflow. */
export function rejectPlan(planId: string, reason?: string) {
  return apiRequest<PlanStatusResponse>(`/api/v1/plans/${planId}/reject`, {
    method: "POST",
    body: reason ? { reason } : {},
  });
}
