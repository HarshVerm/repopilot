import type { PlanResponse, PlanStatusResponse } from "@/types/api";
import { apiRequest } from "./client";

export function getPlan(planId: string, signal?: AbortSignal) {
  return apiRequest<PlanResponse>(`/api/v1/plans/${planId}`, { signal });
}

export function approvePlan(planId: string) {
  return apiRequest<PlanStatusResponse>(`/api/v1/plans/${planId}/approve`, {
    method: "POST",
  });
}

export function rejectPlan(planId: string, reason?: string) {
  return apiRequest<PlanStatusResponse>(`/api/v1/plans/${planId}/reject`, {
    method: "POST",
    body: reason ? { reason } : {},
  });
}
