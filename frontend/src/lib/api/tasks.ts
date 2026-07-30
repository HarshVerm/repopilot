// Module purpose: Provide typed API operations for tasks.

import type {
  CancelTaskResponse,
  CreateTaskRequest,
  TaskListResponse,
  TaskMetricsResponse,
  TaskResponse,
  TaskTimelineResponse,
} from "@/types/api";
import { apiRequest } from "./client";

/** Purpose: List tasks for this frontend workflow. */
export function listTasks(signal?: AbortSignal) {
  return apiRequest<TaskListResponse>("/api/v1/tasks", { signal });
}

/** Purpose: Return task for this frontend workflow. */
export function getTask(taskId: string, signal?: AbortSignal) {
  return apiRequest<TaskResponse>(`/api/v1/tasks/${taskId}`, { signal });
}

/** Purpose: Create task for this frontend workflow. */
export function createTask(request: CreateTaskRequest) {
  return apiRequest<TaskResponse>("/api/v1/tasks", {
    method: "POST",
    body: request,
  });
}

/** Purpose: Cancel task for this frontend workflow. */
export function cancelTask(taskId: string) {
  return apiRequest<CancelTaskResponse>(`/api/v1/tasks/${taskId}/cancel`, {
    method: "POST",
  });
}

/** Purpose: Handle restart task for this frontend module. */
export function restartTask(taskId: string) {
  return apiRequest<TaskResponse>(`/api/v1/tasks/${taskId}/restart`, {
    method: "POST",
  });
}

/** Purpose: Return task timeline for this frontend workflow. */
export function getTaskTimeline(taskId: string, signal?: AbortSignal) {
  return apiRequest<TaskTimelineResponse>(`/api/v1/tasks/${taskId}/timeline`, {
    signal,
  });
}

/** Purpose: Return task metrics for this frontend workflow. */
export function getTaskMetrics(taskId: string, signal?: AbortSignal) {
  return apiRequest<TaskMetricsResponse>(`/api/v1/tasks/${taskId}/metrics`, {
    signal,
  });
}
