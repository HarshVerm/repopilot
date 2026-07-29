import type {
  CancelTaskResponse,
  CreateTaskRequest,
  TaskListResponse,
  TaskMetricsResponse,
  TaskResponse,
  TaskTimelineResponse,
} from "@/types/api";
import { apiRequest } from "./client";

export function listTasks(signal?: AbortSignal) {
  return apiRequest<TaskListResponse>("/api/v1/tasks", { signal });
}

export function getTask(taskId: string, signal?: AbortSignal) {
  return apiRequest<TaskResponse>(`/api/v1/tasks/${taskId}`, { signal });
}

export function createTask(request: CreateTaskRequest) {
  return apiRequest<TaskResponse>("/api/v1/tasks", {
    method: "POST",
    body: request,
  });
}

export function cancelTask(taskId: string) {
  return apiRequest<CancelTaskResponse>(`/api/v1/tasks/${taskId}/cancel`, {
    method: "POST",
  });
}

export function restartTask(taskId: string) {
  return apiRequest<TaskResponse>(`/api/v1/tasks/${taskId}/restart`, {
    method: "POST",
  });
}

export function getTaskTimeline(taskId: string, signal?: AbortSignal) {
  return apiRequest<TaskTimelineResponse>(`/api/v1/tasks/${taskId}/timeline`, {
    signal,
  });
}

export function getTaskMetrics(taskId: string, signal?: AbortSignal) {
  return apiRequest<TaskMetricsResponse>(`/api/v1/tasks/${taskId}/metrics`, {
    signal,
  });
}
