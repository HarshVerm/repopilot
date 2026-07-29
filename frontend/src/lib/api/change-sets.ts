import type { ChangeSetDiffResponse } from "@/types/api";
import { apiRequest } from "./client";

export function getChangeSetDiff(changeSetId: string, signal?: AbortSignal) {
  return apiRequest<ChangeSetDiffResponse>(`/api/v1/change-sets/${changeSetId}/diff`, {
    signal,
  });
}
