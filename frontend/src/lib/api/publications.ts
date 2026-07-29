import type { PublicationResponse } from "@/types/api";
import { apiRequest } from "./client";

export function publishReview(reviewId: string) {
  return apiRequest<PublicationResponse>(`/api/v1/reviews/${reviewId}/publish`, {
    method: "POST",
  });
}

export function publishTask(taskId: string) {
  return apiRequest<PublicationResponse>(`/api/v1/tasks/${taskId}/publish`, {
    method: "POST",
  });
}

export function getPublication(publicationId: string, signal?: AbortSignal) {
  return apiRequest<PublicationResponse>(`/api/v1/publications/${publicationId}`, {
    signal,
  });
}

export function getReviewPublication(reviewId: string, signal?: AbortSignal) {
  return apiRequest<PublicationResponse>(`/api/v1/reviews/${reviewId}/publication`, {
    signal,
  });
}
