// Module purpose: Provide typed API operations for change sets.

import type { ChangeSetDiffResponse } from "@/types/api";
import { apiRequest } from "./client";

/** Purpose: Return change set diff for this frontend workflow. */
export function getChangeSetDiff(changeSetId: string, signal?: AbortSignal) {
  return apiRequest<ChangeSetDiffResponse>(`/api/v1/change-sets/${changeSetId}/diff`, {
    signal,
  });
}
