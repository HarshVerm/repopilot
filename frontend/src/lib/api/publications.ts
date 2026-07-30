// Module purpose: Provide typed API operations for publications.

import type { PublicationResponse } from "@/types/api";
import { apiRequest } from "./client";

/** Purpose: Publish review for this frontend workflow. */
export function publishReview(reviewId: string) {
  return apiRequest<PublicationResponse>(`/api/v1/reviews/${reviewId}/publish`, {
    method: "POST",
  });
}

/** Purpose: Publish task for this frontend workflow. */
export function publishTask(taskId: string) {
  return apiRequest<PublicationResponse>(`/api/v1/tasks/${taskId}/publish`, {
    method: "POST",
  });
}

/** Purpose: Return publication for this frontend workflow. */
export function getPublication(publicationId: string, signal?: AbortSignal) {
  return apiRequest<PublicationResponse>(`/api/v1/publications/${publicationId}`, {
    signal,
  });
}

/** Purpose: Return review publication for this frontend workflow. */
export function getReviewPublication(reviewId: string, signal?: AbortSignal) {
  return apiRequest<PublicationResponse>(`/api/v1/reviews/${reviewId}/publication`, {
    signal,
  });
}
