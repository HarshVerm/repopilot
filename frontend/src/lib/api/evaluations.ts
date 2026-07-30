// Module purpose: Provide typed API operations for evaluations.

import type { EvaluationRunRecordResponse, EvaluationRunResponse } from "@/types/api";
import { apiRequest } from "./client";

/** Purpose: Handle run evaluation for this frontend module. */
export function runEvaluation(body: {
  suite?: string;
  task?: string | null;
  difficulty?: string | null;
  category?: string | null;
  max_tasks?: number | null;
  dry_run?: boolean;
  live?: boolean;
  mark_baseline?: boolean;
}) {
  return apiRequest<EvaluationRunResponse>("/api/v1/evaluations", {
    method: "POST",
    body,
  });
}

/** Purpose: Return evaluation run for this frontend workflow. */
export function getEvaluationRun(evaluationRunId: string, signal?: AbortSignal) {
  return apiRequest<EvaluationRunRecordResponse>(
    `/api/v1/evaluations/${evaluationRunId}`,
    { signal },
  );
}
