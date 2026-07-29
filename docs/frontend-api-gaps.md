# RepoPilot Frontend API Gaps

## Repository Discovery

Required UI capability: browse connected repositories before creating a task.

Existing backend data/API: repository validation and issue listing exist for a manually entered `owner/repo`.

Missing data/API: no endpoint lists repositories available to the authenticated GitHub integration.

Why UI needs it: repository browsing would reduce invalid input and improve task creation.

Minimal recommended backend change: add `GET /api/v1/github/repos` with pagination and search.

## Task Issue Summary

Required UI capability: render issue title, body, labels, and GitHub URL in task tables/details without extra GitHub calls.

Existing backend data/API: task records expose repository owner/name and issue number; GitHub issue lookup exists.

Missing data/API: task response does not include cached issue title/body/url/labels.

Why UI needs it: dashboard rows cannot show issue titles without N+1 GitHub requests.

Minimal recommended backend change: persist a bounded issue snapshot on task creation and expose it in `TaskResponse`.

## Task-Scoped Debug History

Required UI capability: show debugger attempts while a task is debugging or failed.

Existing backend data/API: final review includes `debug_history`; individual debug attempts can be fetched by ID.

Missing data/API: no `GET /api/v1/tasks/{task_id}/debug-attempts` endpoint.

Why UI needs it: debugger tab cannot show history before final review exists.

Minimal recommended backend change: add a task-scoped debug attempt list response with attempt status, diagnosis, changed files, and resulting execution run IDs.

## Publication History Listing

Required UI capability: populate the GitHub screen with publication history.

Existing backend data/API: publications can be fetched by ID or review ID; task list exposes `publication_id`.

Missing data/API: no publication list endpoint.

Why UI needs it: the GitHub screen must derive history from task data and then fetch publications one by one.

Minimal recommended backend change: add `GET /api/v1/publications` with filters for repository, status, and task ID.

## Evaluation History

Required UI capability: show latest benchmark results without inventing metrics.

Existing backend data/API: evaluation runs can be launched and fetched by ID.

Missing data/API: no endpoint lists recent evaluation runs or latest run per suite.

Why UI needs it: evaluations page cannot show live benchmark state after refresh unless the run ID is known.

Minimal recommended backend change: add `GET /api/v1/evaluations?suite=repopilot-eval-v1&limit=10`.

## Create Task Options

Required UI capability: select base branch, network policy, and auto-debug settings when supported.

Existing backend data/API: `CreateTaskRequest` accepts owner, repo, and issue number only.

Missing data/API: no task creation fields for base branch, network policy, or auto-debug.

Why UI needs it: prototype controls for these options cannot be preserved as real controls.

Minimal recommended backend change: only add these fields if the backend state machine and sandbox policy explicitly support them.
