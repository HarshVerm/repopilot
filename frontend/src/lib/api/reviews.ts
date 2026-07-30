// Module purpose: Provide typed API operations for reviews.

import type { FinalReviewResponse, ReviewDecisionResponse } from "@/types/api";
import { apiRequest } from "./client";

/** Purpose: Create final review for this frontend workflow. */
export function createFinalReview(changeSetId: string) {
  return apiRequest<FinalReviewResponse>(`/api/v1/change-sets/${changeSetId}/review`, {
    method: "POST",
  });
}

/** Purpose: Return final review for this frontend workflow. */
export function getFinalReview(reviewId: string, signal?: AbortSignal) {
  return apiRequest<FinalReviewResponse>(`/api/v1/reviews/${reviewId}`, {
    signal,
  });
}

/** Purpose: Approve final review for this frontend workflow. */
export function approveFinalReview(reviewId: string) {
  return apiRequest<ReviewDecisionResponse>(`/api/v1/reviews/${reviewId}/approve`, {
    method: "POST",
  });
}

/** Purpose: Reject final review for this frontend workflow. */
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

/** Purpose: Approve task review for this frontend workflow. */
export function approveTaskReview(
  taskId: string,
  input: ReviewIntegrityInput,
) {
  return apiRequest<ReviewDecisionResponse>(
    `/api/v1/tasks/${taskId}/review/approve`,
    { method: "POST", body: input },
  );
}

/** Purpose: Request task review changes for this frontend workflow. */
export function requestTaskReviewChanges(
  taskId: string,
  input: ReviewIntegrityInput & { feedback: string },
) {
  return apiRequest<ReviewDecisionResponse>(
    `/api/v1/tasks/${taskId}/review/request-changes`,
    { method: "POST", body: input },
  );
}

/** Purpose: Reject task review for this frontend workflow. */
export function rejectTaskReview(
  taskId: string,
  input: ReviewIntegrityInput & { reason?: string },
) {
  return apiRequest<ReviewDecisionResponse>(
    `/api/v1/tasks/${taskId}/review/reject`,
    { method: "POST", body: input },
  );
}
