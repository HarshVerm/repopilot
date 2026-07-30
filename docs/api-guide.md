# API Guide

RepoPilot's backend is a FastAPI application. The browser and any trusted API
client use JSON endpoints under `/api/v1`.

## Interactive documentation

With the backend running locally:

- Swagger UI: `http://localhost:8000/docs`
- OpenAPI JSON: `http://localhost:8000/openapi.json`

The generated documentation is the best source for exact request and response
schemas. This guide explains how the endpoint groups fit together.

## Base URLs

| Context | Base |
| --- | --- |
| Backend directly in local development | `http://localhost:8000` |
| Browser through the frontend proxy | `http://localhost:3000/api/v1` |

## Authentication

The web application uses an HTTP-only session cookie. State-changing requests
also require CSRF protection.

Because authentication is cookie-based, copying an authenticated URL into a
plain `curl` command is usually not enough. Use the browser, a saved cookie jar,
or the generated Swagger interface with the correct session and CSRF values.

## Error format

Expected application errors normally follow this shape:

```json
{
  "detail": {
    "error": {
      "code": "GITHUB_PERMISSION_DENIED",
      "message": "RepoPilot no longer has repository write permission.",
      "details": {}
    }
  }
}
```

Use `code` for program behavior and `message` for users. `details` may contain
safe diagnostic context. It must not contain credentials.

## Health and readiness

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/health` | Confirms the HTTP process is alive |
| GET | `/ready` | Confirms required dependencies are ready |
| GET | `/api/v1/ready` | Versioned readiness endpoint |

Example:

```bash
curl http://localhost:8000/health
curl http://localhost:8000/ready
```

A process can be healthy but not ready, for example when PostgreSQL is
unavailable.

## Authentication endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/v1/auth/github/login` | Begin GitHub OAuth |
| GET | `/api/v1/auth/github/callback` | Complete GitHub OAuth |
| GET | `/api/v1/auth/me` | Return the signed-in user |
| GET | `/api/v1/auth/github/user-authorization` | Inspect user authorization |
| GET | `/api/v1/auth/github/user-authorization/setup` | Repair or begin user authorization |
| POST | `/api/v1/auth/logout` | Revoke the RepoPilot session |
| GET | `/api/v1/auth/github/installations/setup` | Begin GitHub App installation |
| GET | `/api/v1/auth/github/installations/callback` | Complete installation setup |

## GitHub repository endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/v1/github/installations` | List the user's installations |
| POST | `/api/v1/github/installations/{installation_id}/repositories/sync` | Refresh one installation |
| GET | `/api/v1/github/repositories` | List authorized repositories |
| GET | `/api/v1/github/repositories/{repository_id}` | Get one repository |
| GET | `/api/v1/github/repositories/{repository_id}/issues` | List repository issues |
| GET | `/api/v1/github/repositories/{repository_id}/issues/{issue_number}` | Get one issue |

Legacy owner/repository routes also exist under
`/api/v1/github/repos/{owner}/{repo}`. Keep legacy access disabled in production
unless a controlled migration requires it.

## Task endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| POST | `/api/v1/tasks` | Create and start a task |
| GET | `/api/v1/tasks` | List the signed-in user's tasks |
| GET | `/api/v1/tasks/{task_id}` | Get task detail |
| GET | `/api/v1/tasks/{task_id}/timeline` | Get ordered task events |
| GET | `/api/v1/tasks/{task_id}/metrics` | Get task telemetry |
| POST | `/api/v1/tasks/{task_id}/cancel` | Cancel a task |
| POST | `/api/v1/tasks/{task_id}/restart` | Restart a recoverable task |
| POST | `/api/v1/tasks/{task_id}/reconcile` | Reconcile durable artifacts and state |
| POST | `/api/v1/tasks/{task_id}/review/approve` | Approve the final diff |
| POST | `/api/v1/tasks/{task_id}/review/request-changes` | Save feedback and resume coding |
| POST | `/api/v1/tasks/{task_id}/review/reject` | Reject the final diff |
| POST | `/api/v1/tasks/{task_id}/publish` | Publish the approved diff |

The restart endpoint accepts an optional clarification body:

```json
{
  "clarification": "Use the account birth date as the source of truth."
}
```

Clarification is accepted only when the task is in
`plan_revision_required`. If the active plan has `needs_more_context: true`, a
restart without clarification returns `409 PLAN_CONTEXT_REQUIRED` and includes
the planner's questions in `details.missing_context`. A successful clarified
restart preserves the old attempt, marks its plan as superseded, appends the
answer to the original task instructions, and creates a new task attempt.

## Lower-level workflow endpoints

These endpoints expose individual pipeline stages. The task orchestrator
normally coordinates them.

### Repository, index, and retrieval

| Method | Path | Purpose |
| --- | --- | --- |
| POST | `/api/v1/workspaces/clone` | Clone an authorized repository |
| POST | `/api/v1/index/{workspace_id}` | Build a workspace code index |
| GET | `/api/v1/index/{workspace_id}/symbols` | Inspect indexed symbols |
| POST | `/api/v1/retrieval/{workspace_id}/build` | Build retrieval data |
| POST | `/api/v1/retrieval/{workspace_id}/search` | Search repository context |

### Planning and coding

| Method | Path | Purpose |
| --- | --- | --- |
| POST | `/api/v1/workspaces/{workspace_id}/plan` | Generate an execution plan |
| GET | `/api/v1/plans/{plan_id}` | Get a plan |
| POST | `/api/v1/plans/{plan_id}/approve` | Approve a plan |
| POST | `/api/v1/plans/{plan_id}/reject` | Reject a plan |
| POST | `/api/v1/plans/{plan_id}/implement` | Run coding for a plan |
| GET | `/api/v1/change-sets/{change_set_id}/diff` | Get exact proposed diff |

### Verification and debugging

| Method | Path | Purpose |
| --- | --- | --- |
| POST | `/api/v1/change-sets/{change_set_id}/execute` | Verify a change set |
| GET | `/api/v1/execution-runs/{execution_run_id}` | Get verification results |
| POST | `/api/v1/execution-runs/{execution_run_id}/debug` | Start a debug attempt |
| GET | `/api/v1/debug-attempts/{debug_attempt_id}` | Get a debug attempt |

### Review and publication

| Method | Path | Purpose |
| --- | --- | --- |
| POST | `/api/v1/change-sets/{change_set_id}/review` | Create a final review |
| GET | `/api/v1/reviews/{review_id}` | Get a review |
| POST | `/api/v1/reviews/{review_id}/approve` | Approve a review |
| POST | `/api/v1/reviews/{review_id}/reject` | Reject a review |
| POST | `/api/v1/reviews/{review_id}/publish` | Publish an approved review |
| GET | `/api/v1/publications/{publication_id}` | Get publication result |
| GET | `/api/v1/reviews/{review_id}/publication` | Get a review's publication |

## Evaluation endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| POST | `/api/v1/evaluations` | Start an evaluation run |
| GET | `/api/v1/evaluations/{evaluation_id}` | Read evaluation results |

See [Evaluation Guide](../backend/docs/evaluation.md) for the evaluation
workflow.

## Common HTTP status codes

| Status | Meaning in RepoPilot |
| --- | --- |
| 200/201 | Operation succeeded |
| 400 | Invalid request or state transition |
| 401 | No valid RepoPilot session |
| 403 | Signed-in user lacks access or GitHub denied permission |
| 404 | Resource does not exist or is not visible to this user |
| 409 | Duplicate operation, stale-state conflict, or required workflow context is missing |
| 422 | Request body does not match the schema |
| 503 | Required integration is not configured or dependency is unavailable |
| 500 | Unexpected server error; inspect the backend traceback |

## Adding an endpoint

1. Define request and response schemas.
2. Add the route under `backend/app/api/v1`.
3. Put business behavior in a service, not the route.
4. Require the current user and enforce resource ownership.
5. Add CSRF protection for state changes.
6. Return stable domain error codes.
7. Add unit or integration tests.
8. Add the frontend client and query/mutation only after the contract is clear.
9. Update this guide if the endpoint is user-facing.
