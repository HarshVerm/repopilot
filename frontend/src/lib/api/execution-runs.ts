// Module purpose: Provide typed API operations for execution runs.

import type { ExecutionRunResponse } from "@/types/api";
import { apiRequest } from "./client";

/** Purpose: Return execution run for this frontend workflow. */
export function getExecutionRun(executionRunId: string, signal?: AbortSignal) {
  return apiRequest<ExecutionRunResponse>(
    `/api/v1/execution-runs/${executionRunId}`,
    { signal },
  );
}
