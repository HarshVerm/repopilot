import type { ExecutionRunResponse } from "@/types/api";
import { apiRequest } from "./client";

export function getExecutionRun(executionRunId: string, signal?: AbortSignal) {
  return apiRequest<ExecutionRunResponse>(
    `/api/v1/execution-runs/${executionRunId}`,
    { signal },
  );
}
