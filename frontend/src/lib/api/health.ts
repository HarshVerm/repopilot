import type { HealthResponse, ReadinessResponse } from "@/types/api";
import { apiRequest } from "./client";

export function getHealth(signal?: AbortSignal) {
  return apiRequest<HealthResponse>("/health", { signal });
}

export function getReadiness(signal?: AbortSignal) {
  return apiRequest<ReadinessResponse>("/ready", { signal });
}
