# Backend guide

The backend is a Python 3.11 FastAPI application using asynchronous SQLAlchemy
and PostgreSQL.

## Folder map

```text
backend/
├── app/
│   ├── agents/          Planner, coder, and debugger agent configuration
│   ├── api/routes/      HTTP endpoints grouped by feature
│   ├── core/            Environment-backed settings
│   ├── db/models/       SQLAlchemy database models
│   ├── evaluation/      Evaluation runner, metrics, and reports
│   ├── observability/   Logging, IDs, pricing, and redaction
│   ├── schemas/         Pydantic request and response types
│   ├── security/        Security regression definitions
│   ├── services/        Application and domain behavior
│   └── main.py          FastAPI application entry point
├── migrations/          Alembic database migrations
├── tests/               Pytest test suite
├── evals/               AI evaluation datasets and fixtures
└── scripts/             Command-line tools
```

## Application startup

`backend/app/main.py` performs four important actions:

1. Validates startup limits and production security configuration.
2. Configures structured task logging.
3. Creates the FastAPI application and CORS policy.
4. Includes the API routes and correlation-ID middleware.

Run it with:

```bash
cd backend
python -m uvicorn app.main:app --reload --port 8000
```

## API routes

Route modules should remain thin. They:

- receive and validate Pydantic payloads;
- require the current user when appropriate;
- validate CSRF on cookie-authenticated mutations;
- resolve user-owned repositories or tasks;
- call a service;
- translate known errors into stable HTTP errors.

Business logic belongs in `app/services/`, not inside route functions.

## Service map

| Directory | Responsibility |
| --- | --- |
| `services/auth/` | OAuth state, sessions, encrypted GitHub user tokens, ownership |
| `services/github/` | GitHub App JWTs, installation tokens, repository sync and permissions |
| `services/workspace/` | Safe task-specific repository clones |
| `services/indexing/` | File scanning, Tree-sitter parsing and symbols |
| `services/chunking/` | Token-aware source chunks |
| `services/embeddings/` | Embedding provider boundary |
| `services/retrieval/` | Structural, lexical and semantic RAG |
| `services/planning/` | Planner inputs, agent execution and validation |
| `services/changes/` | Safe edits, diffs, hashes and policies |
| `services/sandbox/` | Command detection and Docker verification |
| `services/debugging/` | Failure classification and bounded correction |
| `services/reviews/` | Exact final review and request-changes behavior |
| `services/publishing/` | Integrity checks, Git branch/commit/push and pull request |
| `services/tasks/` | Task creation, state machine, workflow, locking and recovery |
| `services/hardening/` | Limits, retries, rate limits and readiness |
| `services/cleanup/` | Workspace cleanup |

## Agents

RepoPilot uses three specialized AI roles:

| Agent | Job |
| --- | --- |
| Planner | Convert the issue and retrieved context into a bounded plan |
| Coder | Apply safe file operations that satisfy the approved plan |
| Debugger | Interpret failed verification and attempt bounded corrections |

Agent output is treated as untrusted input. Services validate schemas, file
paths, modification policy, patch limits, workspace state, and task state
before accepting it.

## Task lifecycle ownership

Only backend task services perform state transitions:

- `TaskService` persists tasks and events.
- `TaskStateMachine` validates allowed transitions.
- `TaskWorkflowService` calls the stages in order.
- `TaskOperationLockService` prevents duplicate workflow/publication work.
- `TaskReconciler` detects stale or interrupted tasks.

The frontend can request an action, but it cannot assign a task status.

## Database access

`app/db/session.py` creates the async engine and session factory. Route
dependencies receive one `AsyncSession`. Background workflows create their own
session because the request session is closed after the response.

When adding database behavior:

1. Add or update a model.
2. Create an Alembic migration.
3. Update the corresponding Pydantic schema.
4. Put business logic in a service.
5. Add route and service tests.

## Error handling

Expected failures should use a stable error code and useful message. The
frontend reads:

```json
{
  "detail": {
    "error": {
      "code": "EXAMPLE_CODE",
      "message": "A useful explanation.",
      "details": {}
    }
  }
}
```

Unexpected exceptions are logged with request, correlation, task, stage, and
error-type context. Secrets and untrusted content must be redacted or bounded.

## Observability

The observability package provides:

- correlation IDs across an HTTP request;
- request IDs supplied by the frontend;
- structured task and failure logs;
- sensitive-value redaction;
- token, latency, and estimated-cost telemetry.

`TaskEvent` is the user-visible timeline. Avoid writing duplicate events for
one logical transition.

## Security boundaries

Backend checks include:

- session and CSRF validation;
- user → installation → repository → task authorization;
- OAuth state expiry and single use;
- encrypted GitHub user tokens;
- short-lived installation tokens;
- safe workspace path resolution;
- repository/file/chunk/patch limits;
- sandbox resource and network limits;
- exact diff and base-commit checks before publication;
- rate limits and bounded provider retries.

## Adding a feature

For a new backend feature:

1. Define input/output schemas in `app/schemas/`.
2. Implement behavior in a focused service.
3. Add a thin route in `app/api/routes/`.
4. Register a new router in `app/api/router.py` if needed.
5. Use `TaskService` for task changes.
6. Add tests for success, authorization failure, validation failure, and
   idempotency/concurrency where relevant.
7. Update the appropriate Markdown guide.

## Useful entry files

- `app/main.py`: application startup
- `app/api/router.py`: route registration
- `app/core/config.py`: settings and limits
- `app/services/tasks/workflow.py`: complete automatic workflow
- `app/services/tasks/state_machine.py`: valid task transitions
- `app/services/retrieval/service.py`: RAG orchestration
- `app/services/reviews/service.py`: final review
- `app/services/publishing/service.py`: publication

See [API guide](api-guide.md) and [Database guide](database-guide.md) next.
