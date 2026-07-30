// Module purpose: Define shared api TypeScript contracts.

export type TaskStatus =
  | "created"
  | "repository_preparing"
  | "repository_ready"
  | "indexing"
  | "indexed"
  | "retrieving"
  | "planning"
  | "plan_pending_approval"
  | "plan_approved"
  | "plan_rejected"
  | "plan_revision_required"
  | "coding"
  | "patch_generated"
  | "testing"
  | "test_failed"
  | "debugging"
  | "verification_passed"
  | "review_pending"
  | "review_approved"
  | "review_rejected"
  | "publishing"
  | "completed"
  | "failed"
  | "cancelled";

export interface TaskResponse {
  task_id: string;
  repository: {
    owner: string;
    repo: string;
  };
  repository_id: string | null;
  installation_id: string | null;
  issue_number: number;
  issue: {
    github_issue_id: number | null;
    number: number;
    title: string | null;
    body: string | null;
    html_url: string | null;
    author: string | null;
    labels: string[];
    created_at: string | null;
    updated_at_at_creation: string | null;
  } | null;
  issue_summary: string | null;
  user_instructions: string | null;
  autonomy_mode: "standard" | "strict";
  base_branch: string | null;
  base_commit_sha: string | null;
  workspace_id: string | null;
  status: TaskStatus;
  current_step: number;
  started_at: string | null;
  completed_at: string | null;
  cancelled_at: string | null;
  last_error: string | null;
  last_error_type: string | null;
  failure_category: string | null;
  retryable: boolean | null;
  cancel_requested: boolean;
  version: number;
  active_plan_id: string | null;
  active_change_set_id: string | null;
  active_execution_run_id: string | null;
  active_review_id: string | null;
  publication_id: string | null;
  last_event_at: string | null;
  created_at: string | null;
  updated_at: string | null;
  metrics: Record<string, unknown> | null;
}

export interface TaskListResponse {
  tasks: TaskResponse[];
}

export interface CreateTaskRequest {
  repository_id: string;
  issue_number: number;
  user_instructions?: string;
}

export interface CancelTaskResponse {
  task_id: string;
  status: TaskStatus;
  cancel_requested: boolean;
}

export interface TaskTimelineEventResponse {
  event_id: string;
  task_id: string;
  event_type: string;
  step: number | null;
  status: string | null;
  message: string | null;
  metadata: Record<string, unknown>;
  request_id: string | null;
  correlation_id: string | null;
  agent_run_id: string | null;
  created_at: string | null;
}

export interface TaskTimelineResponse {
  task_id: string;
  events: TaskTimelineEventResponse[];
}

export interface TaskMetricsResponse {
  task_id: string;
  metrics: Record<string, unknown>;
}

export interface RepositoryResponse {
  id: number;
  name: string;
  full_name: string;
  description: string | null;
  private: boolean;
  default_branch: string;
  clone_url: string;
  language: string | null;
  stars: number;
}

export interface IssueResponse {
  id: number;
  number: number;
  title: string;
  body: string | null;
  state: string;
  html_url: string;
  comments: number;
  labels: string[];
  author: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface CurrentUserResponse {
  user_id: string;
  github_user_id: number;
  github_login: string;
  github_name: string | null;
  github_avatar_url: string | null;
  github_email: string | null;
}

export interface GitHubUserAuthorizationResponse {
  connected: boolean;
  status: string;
  attributed_login: string;
  access_token_expires_at: string | null;
  refresh_token_expires_at: string | null;
}

export interface GitHubInstallationResponse {
  id: string;
  github_installation_id: number;
  account_id: number;
  account_login: string;
  account_type: string;
  target_type: string | null;
  repository_selection: string;
  status: string;
  suspended_at: string | null;
  repository_count: number;
}

export interface GitHubInstallationListResponse {
  installations: GitHubInstallationResponse[];
}

export interface ConnectedRepositoryResponse {
  id: string;
  installation_id: string;
  github_repository_id: number;
  owner: string;
  name: string;
  full_name: string;
  private: boolean;
  archived: boolean;
  disabled: boolean;
  default_branch: string;
  html_url: string;
  permissions: Record<string, boolean>;
  access_status: string;
  last_synced_at: string | null;
}

export interface ConnectedRepositoryListResponse {
  repositories: ConnectedRepositoryResponse[];
  page: number;
  per_page: number;
  total: number;
  has_next: boolean;
}

export interface IssueListResponse {
  issues: IssueResponse[];
  page: number;
  per_page: number;
  has_next: boolean;
}

export interface RepositoryFileListResponse {
  files: string[];
  total: number;
  truncated: boolean;
  default_branch: string;
}

export interface CreateIssueRequest {
  title: string;
  description: string;
  related_files: string[];
}

export interface SourceReference {
  file_path: string;
  start_line: number | null;
  end_line: number | null;
}

export interface PlannedFile {
  path: string;
  change_type: "modify" | "create";
  reason: string;
  references: SourceReference[];
}

export interface ImplementationStep {
  order: number;
  description: string;
  files: string[];
}

export interface TestPlanItem {
  description: string;
  test_type: string;
}

export interface PlannerOutput {
  summary: string;
  problem_analysis: string;
  likely_root_cause: string | null;
  confidence: number;
  files_to_inspect: PlannedFile[];
  files_to_modify: PlannedFile[];
  implementation_steps: ImplementationStep[];
  tests: TestPlanItem[];
  risks: string[];
  assumptions: string[];
  needs_more_context: boolean;
  missing_context: string[];
}

export interface PlannerExecutionMetadata {
  model: string | null;
  latency_ms: number | null;
  input_tokens: number | null;
  output_tokens: number | null;
  total_tokens: number | null;
  trace_include_sensitive_data: boolean;
}

export interface PlanResponse {
  plan_id: string;
  status: "draft" | "pending_approval" | "approved" | "rejected" | "superseded" | string;
  workspace_id: string;
  owner: string;
  repo: string;
  issue_number: number;
  plan: PlannerOutput;
  rejection_reason: string | null;
  metadata: PlannerExecutionMetadata;
}

export interface PlanStatusResponse {
  plan_id: string;
  status: string;
  rejection_reason: string | null;
}

export interface ChangeSetFileResponse {
  path: string;
  before_sha256: string;
  after_sha256: string;
  lines_added: number;
  lines_deleted: number;
}

export interface ChangeSetDiffResponse {
  change_set_id: string;
  plan_id: string;
  base_commit_sha: string;
  files_changed: ChangeSetFileResponse[];
  lines_added: number;
  lines_deleted: number;
  diff: string | null;
  tests_run: boolean;
}

export interface CommandResultResponse {
  name: string;
  command_type: string;
  status: string;
  exit_code: number | null;
  duration_ms: number;
  stdout: string;
  stderr: string;
  stdout_truncated: boolean;
  stderr_truncated: boolean;
}

export interface ExecutionRunResponse {
  execution_run_id: string;
  change_set_id: string;
  workspace_id: string;
  status: string;
  checks: Record<string, string>;
  duration_ms: number | null;
  commands: Record<string, unknown>[];
  results: CommandResultResponse[];
  timed_out: boolean;
  error_message: string | null;
}

export interface FinalReviewResponse {
  review_id: string;
  status: "pending_review" | "approved" | "rejected" | "superseded" | string;
  review_version: number;
  issue: Record<string, unknown>;
  plan: Record<string, unknown>;
  changes: Record<string, unknown>;
  verification: Record<string, unknown>;
  debug_history: Record<string, unknown>;
  risk_summary: string;
  base_commit_sha: string;
  diff_hash: string;
  diff: string;
  diff_truncated: boolean;
  full_diff_available: boolean;
  created_at: string | null;
  reviewed_at: string | null;
  decision: string | null;
  rejection_reason: string | null;
  feedback: string | null;
}

export interface ReviewDecisionResponse {
  review_id: string;
  status: string;
  decision: string | null;
  reviewed_at: string | null;
  rejection_reason: string | null;
  feedback: string | null;
}

export interface PublicationResponse {
  publication_id: string;
  review_id: string;
  workspace_id: string;
  plan_id: string;
  change_set_id: string;
  status: string;
  repository: Record<string, unknown>;
  base_branch: string | null;
  head_branch: string | null;
  base_commit_sha: string;
  approved_diff_hash: string;
  working_tree_diff_hash: string | null;
  staged_diff_hash: string | null;
  commit_diff_hash: string | null;
  commit_sha: string | null;
  remote_head_sha: string | null;
  pull_request_number: number | null;
  pull_request_url: string | null;
  pull_request_author_login: string | null;
  retry_count: number;
  error_message: string | null;
  failure_stage: string | null;
  failure_reason: string | null;
  created_at: string | null;
  updated_at: string | null;
  remote_branch_created_at: string | null;
  pr_created_at: string | null;
  published_at: string | null;
}

export interface ReadinessComponent {
  status: string;
  details: string | null;
}

export interface ReadinessResponse {
  status: string;
  checks: Record<string, ReadinessComponent>;
}

export interface HealthResponse {
  status: string;
}

export interface EvaluationRunResponse {
  run_id: string;
  report: Record<string, unknown>;
  paths: Record<string, string>;
}

export interface EvaluationRunRecordResponse {
  run_id: string;
  suite_name: string;
  suite_version: string;
  status: string;
  report: Record<string, unknown> | null;
}
