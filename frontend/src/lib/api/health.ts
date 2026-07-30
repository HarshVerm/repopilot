// Module purpose: Provide typed API operations for health.

import type { HealthResponse, ReadinessResponse } from "@/types/api";
import { apiRequest } from "./client";

/** Purpose: Return health for this frontend workflow. */
export function getHealth(signal?: AbortSignal) {
  return apiRequest<HealthResponse>("/health", { signal });
}

/** Purpose: Return readiness for this frontend workflow. */
export function getReadiness(signal?: AbortSignal) {
  return apiRequest<ReadinessResponse>("/ready", { signal });
}
