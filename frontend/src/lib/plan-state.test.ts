import assert from "node:assert/strict";
import { describe, it } from "node:test";
import type { PlanResponse } from "@/types/api";
import { canApprovePlan, planNeedsClarification } from "./plan-state";

function plan(
  overrides: Partial<PlanResponse["plan"]> = {},
  status: PlanResponse["status"] = "pending_approval",
): PlanResponse {
  return {
    plan_id: "plan-1",
    status,
    workspace_id: "workspace-1",
    owner: "owner",
    repo: "repo",
    issue_number: 1,
    rejection_reason: null,
    metadata: {
      model: null,
      latency_ms: null,
      input_tokens: null,
      output_tokens: null,
      total_tokens: null,
      trace_include_sensitive_data: false,
    },
    plan: {
      summary: "Plan",
      problem_analysis: "Analysis",
      likely_root_cause: null,
      confidence: 0.8,
      files_to_inspect: [],
      files_to_modify: [],
      implementation_steps: [],
      tests: [],
      risks: [],
      assumptions: [],
      needs_more_context: false,
      missing_context: [],
      ...overrides,
    },
  };
}

describe("plan review state", () => {
  it("allows a normal pending plan to be approved", () => {
    assert.equal(
      canApprovePlan("plan_pending_approval", plan()),
      true,
    );
  });

  it("blocks approval while the planner needs clarification", () => {
    const blocked = plan({
      needs_more_context: true,
      missing_context: ["Which behavior is expected?"],
    });

    assert.equal(planNeedsClarification(blocked), true);
    assert.equal(
      canApprovePlan("plan_pending_approval", blocked),
      false,
    );
  });

  it("requires the task and plan states to agree", () => {
    assert.equal(
      canApprovePlan("plan_revision_required", plan()),
      false,
    );
    assert.equal(
      canApprovePlan("plan_pending_approval", plan({}, "approved")),
      false,
    );
  });
});
