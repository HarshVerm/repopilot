import type { FinalReviewResponse, ReviewDecisionResponse } from "@/types/api";
import { apiRequest } from "./client";

export function createFinalReview(changeSetId: string) {
  return apiRequest<FinalReviewResponse>(`/api/v1/change-sets/${changeSetId}/review`, {
    method: "POST",
  });
}

export function getFinalReview(reviewId: string, signal?: AbortSignal) {
  return apiRequest<FinalReviewResponse>(`/api/v1/reviews/${reviewId}`, {
    signal,
  });
}

export function approveFinalReview(reviewId: string) {
  return apiRequest<ReviewDecisionResponse>(`/api/v1/reviews/${reviewId}/approve`, {
    method: "POST",
  });
}

export function rejectFinalReview(reviewId: string, reason?: string) {
  return apiRequest<ReviewDecisionResponse>(`/api/v1/reviews/${reviewId}/reject`, {
    method: "POST",
    body: reason ? { reason } : {},
  });
}

export interface ReviewIntegrityInput {
  review_id: string;
  changeset_id: string;
  diff_hash: string;
}

export function approveTaskReview(
  taskId: string,
  input: ReviewIntegrityInput,
) {
  return apiRequest<ReviewDecisionResponse>(
    `/api/v1/tasks/${taskId}/review/approve`,
    { method: "POST", body: input },
  );
}

export function requestTaskReviewChanges(
  taskId: string,
  input: ReviewIntegrityInput & { feedback: string },
) {
  return apiRequest<ReviewDecisionResponse>(
    `/api/v1/tasks/${taskId}/review/request-changes`,
    { method: "POST", body: input },
  );
}

export function rejectTaskReview(
  taskId: string,
  input: ReviewIntegrityInput & { reason?: string },
) {
  return apiRequest<ReviewDecisionResponse>(
    `/api/v1/tasks/${taskId}/review/reject`,
    { method: "POST", body: input },
  );
}
