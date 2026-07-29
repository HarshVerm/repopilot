import assert from "node:assert/strict";
import { describe, it } from "node:test";
import type { TaskResponse } from "@/types/api";
import {
  getTaskLifecycle,
  isActiveTask,
  isRestartableStatus,
  isTerminalTask,
  isWaitingForHuman,
} from "./task-status";

function task(status: TaskResponse["status"]): TaskResponse {
  return {
    task_id: "task-1",
    repository: { owner: "owner", repo: "repo" },
    repository_id: null,
    installation_id: null,
    issue_number: 1,
    issue: null,
    issue_summary: null,
    user_instructions: null,
    autonomy_mode: "standard",
    base_branch: null,
    base_commit_sha: null,
    workspace_id: null,
    status,
    current_step: 1,
    started_at: null,
    completed_at: null,
    cancelled_at: null,
    last_error: null,
    last_error_type: null,
    failure_category: null,
    retryable: null,
    cancel_requested: false,
    version: 1,
    active_plan_id: null,
    active_change_set_id: null,
    active_execution_run_id: null,
    active_review_id: null,
    publication_id: null,
    last_event_at: null,
    created_at: null,
    updated_at: null,
    metrics: null,
  };
}

describe("task lifecycle mapping", () => {
  it("marks plan approval as waiting when task is pending plan approval", () => {
    const lifecycle = getTaskLifecycle(task("plan_pending_approval"));
    assert.equal(lifecycle.find((stage) => stage.id === "plan_approval")?.state, "waiting");
    assert.equal(lifecycle.find((stage) => stage.id === "coding")?.state, "upcoming");
  });

  it("does not complete publishing after final review is merely approved", () => {
    const lifecycle = getTaskLifecycle(task("review_approved"));
    assert.equal(lifecycle.find((stage) => stage.id === "final_review")?.state, "waiting");
    assert.equal(lifecycle.find((stage) => stage.id === "publishing")?.state, "upcoming");
  });

  it("marks failed status without completing future stages", () => {
    const lifecycle = getTaskLifecycle(task("plan_rejected"));
    assert.equal(lifecycle.find((stage) => stage.id === "plan_approval")?.state, "failed");
    assert.equal(lifecycle.find((stage) => stage.id === "coding")?.state, "upcoming");
  });

  it("shows the actual failed stage from the failure category", () => {
    const failedTask = task("failed");
    failedTask.failure_category = "planner_error";
    const lifecycle = getTaskLifecycle(failedTask);

    assert.equal(lifecycle.find((stage) => stage.id === "planning")?.state, "failed");
    assert.equal(lifecycle.find((stage) => stage.id === "plan_approval")?.state, "upcoming");
    assert.equal(lifecycle.find((stage) => stage.id === "publishing")?.state, "upcoming");
  });

  it("uses the persisted step when an unknown failure has no category", () => {
    const failedTask = task("failed");
    failedTask.current_step = 7;
    const lifecycle = getTaskLifecycle(failedTask);

    assert.equal(lifecycle.find((stage) => stage.id === "verification")?.state, "failed");
    assert.equal(lifecycle.find((stage) => stage.id === "final_review")?.state, "upcoming");
    assert.equal(lifecycle.find((stage) => stage.id === "publishing")?.state, "upcoming");
  });

  it("shows plan revision required as stopped rather than active planning", () => {
    const lifecycle = getTaskLifecycle(task("plan_revision_required"));

    assert.equal(lifecycle.find((stage) => stage.id === "planning")?.state, "failed");
    assert.equal(lifecycle.find((stage) => stage.id === "plan_approval")?.state, "upcoming");
    assert.equal(isActiveTask(task("plan_revision_required")), false);
    assert.equal(isWaitingForHuman(task("plan_revision_required")), true);
  });

  it("classifies active, waiting, and terminal task states", () => {
    assert.equal(isActiveTask(task("coding")), true);
    assert.equal(isWaitingForHuman(task("review_pending")), true);
    assert.equal(isTerminalTask(task("cancelled")), true);
  });

  it("allows manual restart for stopped tasks that can start a new attempt", () => {
    assert.equal(isRestartableStatus("failed"), true);
    assert.equal(isRestartableStatus("cancelled"), true);
    assert.equal(isRestartableStatus("plan_revision_required"), true);
    assert.equal(isRestartableStatus("completed"), false);
    assert.equal(isRestartableStatus("planning"), false);
  });
});
