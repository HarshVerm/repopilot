import assert from "node:assert/strict";
import { describe, it } from "node:test";
import type { PublicationResponse, TaskResponse } from "@/types/api";
import { canRetryPublication, getAvailableTaskActions } from "./task-actions";

function task(overrides: Partial<TaskResponse>): TaskResponse {
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
    status: "created",
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
    ...overrides,
  };
}

function publication(
  overrides: Partial<PublicationResponse>,
): PublicationResponse {
  return {
    publication_id: "pub-1",
    review_id: "review-1",
    workspace_id: "workspace-1",
    plan_id: "plan-1",
    change_set_id: "change-1",
    status: "failed",
    repository: {},
    base_branch: "main",
    head_branch: null,
    base_commit_sha: "abc",
    approved_diff_hash: "def",
    working_tree_diff_hash: null,
    staged_diff_hash: null,
    commit_diff_hash: null,
    commit_sha: null,
    remote_head_sha: null,
    pull_request_number: null,
    pull_request_url: null,
    retry_count: 0,
    error_message: null,
    failure_stage: null,
    failure_reason: null,
    created_at: null,
    updated_at: null,
    remote_branch_created_at: null,
    pr_created_at: null,
    published_at: null,
    ...overrides,
  };
}

describe("available task actions", () => {
  it("shows plan review only for pending plan approval with a plan id", () => {
    const actions = getAvailableTaskActions(
      task({ status: "plan_pending_approval", active_plan_id: "plan-1" }),
    );
    assert.equal(actions.map((action) => action.id).includes("review_plan"), true);
    assert.equal(actions.map((action) => action.id).includes("cancel_task"), true);
  });

  it("shows final diff review for review pending without publishing", () => {
    const actions = getAvailableTaskActions(
      task({ status: "review_pending", active_review_id: "review-1" }),
    );
    assert.equal(actions.map((action) => action.id).includes("review_final_diff"), true);
    assert.equal(actions.map((action) => action.id).includes("publish_pull_request"), false);
  });

  it("shows publish only after review approval", () => {
    const actions = getAvailableTaskActions(
      task({ status: "review_approved", active_review_id: "review-1" }),
    );
    assert.equal(actions.map((action) => action.id).includes("publish_pull_request"), true);
    assert.equal(actions.map((action) => action.id).includes("review_final_diff"), false);
  });

  it("shows open pull request only when completed task has real publication url", () => {
    const actions = getAvailableTaskActions(
      task({ status: "completed" }),
      publication({
        status: "published",
        head_branch: "repopilot/task",
        commit_sha: "abc123",
        pull_request_number: 42,
        pull_request_url: "https://github.com/owner/repo/pull/42",
      }),
    );
    assert.deepEqual(actions.map((action) => action.id), ["open_pull_request"]);
  });

  it("offers a publication retry for a failed publication without restarting the task", () => {
    const failedTask = task({
      status: "failed",
      active_review_id: "review-1",
      publication_id: "pub-1",
      retryable: true,
    });
    const failedPublication = publication({ status: "failed" });
    const actions = getAvailableTaskActions(failedTask, failedPublication);

    assert.equal(canRetryPublication(failedTask, failedPublication), true);
    assert.deepEqual(actions.map((action) => action.label), ["Retry Publishing"]);
  });

  it("does not offer publication retry for an unrelated failed task", () => {
    const failedTask = task({
      status: "failed",
      active_review_id: "review-1",
      retryable: true,
    });

    assert.equal(canRetryPublication(failedTask, null), false);
    assert.deepEqual(getAvailableTaskActions(failedTask, null), []);
  });

  it("offers retry when pull-request creation partially published", () => {
    const publishingTask = task({
      status: "publishing",
      active_review_id: "review-1",
      publication_id: "pub-1",
    });
    const partialPublication = publication({ status: "partially_published" });

    assert.equal(canRetryPublication(publishingTask, partialPublication), true);
    assert.deepEqual(
      getAvailableTaskActions(publishingTask, partialPublication).map(
        (action) => action.label,
      ),
      ["Retry Publishing"],
    );
  });
});
