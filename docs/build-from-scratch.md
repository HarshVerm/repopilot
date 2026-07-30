# Build RepoPilot From Scratch

This guide is the implementation blueprint for a development team that wants
to create a RepoPilot-style product in a new repository. It explains the order
in which to build the system, what each part must do, and the acceptance gate
for every phase.

The developers can write all product code manually. They do not need to use an
AI coding assistant while developing it. The finished product still needs an
AI model provider at runtime because planning, coding, embeddings, and
debugging are product features.

This is not a quick-start guide for running the existing repository. Use
[Getting Started](getting-started.md) for that. This guide describes how to
reproduce the architecture from an empty directory.

## 1. Freeze the product contract before writing code

Write and approve this product flow:

```text
GitHub login
→ GitHub App installation
→ Repository selection
→ GitHub issue selection
→ Optional user instructions
→ Create task
→ Clone repository
→ Index code
→ Retrieve relevant code
→ Plan
→ Code in an isolated workspace
→ Verify in Docker
→ Debug failures within a limit
→ Human reviews the exact diff
→ Approve, reject, or request changes
→ If approved, explicitly publish a pull request
```

Record these non-negotiable rules:

1. The backend is authoritative for task state.
2. GitHub OAuth identifies the user.
3. A GitHub App installation determines repository access.
4. No GitHub, database, encryption, or AI secret reaches browser JavaScript.
5. One user cannot access another user's repository, task, artifacts, or
   workspace.
6. Issue text, repository text, and user instructions are untrusted input.
7. Models cannot directly commit, push, open, or merge pull requests.
8. Human approval is tied to one exact diff hash.
9. Publication rechecks the repository, permission, base commit, and diff.
10. The application never automatically merges a pull request.

Do not begin the workflow implementation until the team agrees to these rules.
They determine the database, API, and security design.

## 2. Choose the initial architecture

Build the first version as a **modular monolith**:

```mermaid
flowchart LR
    Browser[Browser]
    Web[Next.js application]
    API[FastAPI modular monolith]
    DB[(PostgreSQL and pgvector)]
    GitHub[GitHub APIs]
    Models[AI model APIs]
    Workspace[Task workspaces]
    Docker[Docker sandbox]

    Browser --> Web
    Web --> API
    API --> DB
    API --> GitHub
    API --> Models
    API --> Workspace
    API --> Docker
```

Use:

- Python 3.11 and FastAPI for the backend;
- asynchronous SQLAlchemy and Alembic;
- PostgreSQL with pgvector;
- Next.js App Router, React, and TypeScript;
- TanStack Query for browser server-state management;
- Git and one isolated workspace per task;
- Docker for untrusted repository verification;
- GitHub OAuth plus a GitHub App;
- structured model outputs for the planner, coder, and debugger.

Do not start with microservices. Authentication, state transitions, artifact
creation, and publication require transactions and strong invariants. Separate
workers can be introduced after the workflow is correct.

### Dependency direction

Keep this dependency direction:

```text
frontend page/component
→ typed frontend API function
→ FastAPI route
→ domain service
→ model/repository
→ PostgreSQL
```

Routes validate HTTP input and translate errors. Services own business rules.
Models persist state. Components display server state.

## 3. Create the empty project

Create this initial layout:

```text
repopilot/
├── backend/
│   ├── app/
│   │   ├── agents/
│   │   ├── api/routes/
│   │   ├── core/
│   │   ├── db/models/
│   │   ├── evaluation/
│   │   ├── observability/
│   │   ├── schemas/
│   │   ├── security/
│   │   └── services/
│   ├── migrations/
│   ├── tests/
│   └── scripts/
├── frontend/
├── docs/
├── .env.example
├── .gitignore
├── docker-compose.yml
└── README.md
```

One possible bootstrap sequence is:

```bash
mkdir repopilot
cd repopilot
git init
mkdir -p backend/app backend/tests backend/migrations docs
npx create-next-app@16.2.12 frontend \
  --typescript --tailwind --eslint --app --src-dir --use-npm
python3.11 -m venv backend/.venv
```

Install backend packages by capability instead of copying a large dependency
list without understanding it:

| Capability | Main packages |
| --- | --- |
| HTTP API | `fastapi`, `uvicorn`, `pydantic`, `pydantic-settings` |
| Database | `sqlalchemy`, `asyncpg`, `alembic`, `pgvector` |
| GitHub and providers | `httpx`, `PyJWT`, `cryptography` |
| AI | `openai`, `openai-agents` |
| RAG | `tiktoken`, Tree-sitter language packages |
| Testing | `pytest`, async test support, HTTP test client |

Pin and review versions in `backend/requirements.txt`. Keep development-only
tools in `backend/requirements-dev.txt`.

Create a local PostgreSQL service:

```yaml
services:
  postgres:
    image: pgvector/pgvector:pg17
    environment:
      POSTGRES_DB: repopilot
      POSTGRES_USER: repopilot
      POSTGRES_PASSWORD: repopilot
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data

volumes:
  postgres_data:
```

### Phase gate

- The empty FastAPI application returns `{"status": "healthy"}` from
  `/health`.
- The Next.js home page renders.
- PostgreSQL starts through Compose.
- The backend can open and close an async database session.
- Backend and frontend checks run in CI.

## 4. Build configuration, errors, and observability first

Before domain features, implement the shared operational foundation.

### Environment settings

Create one typed settings object. Include:

```dotenv
APP_ENV=development
TASK_LOG_LEVEL=INFO
APP_BASE_URL=http://localhost:8000
FRONTEND_URL=http://localhost:3000
SESSION_SECRET=
COOKIE_SECURE=false
COOKIE_DOMAIN=
ALLOW_LEGACY_UNAUTHENTICATED_API=false

GITHUB_APP_ID=
GITHUB_APP_PRIVATE_KEY_PATH=
GITHUB_APP_CLIENT_ID=
GITHUB_APP_CLIENT_SECRET=
GITHUB_APP_SLUG=
GITHUB_USER_TOKEN_ENCRYPTION_SECRET=

OPENAI_API_KEY=
DATABASE_URL=postgresql+asyncpg://repopilot:repopilot@localhost:5432/repopilot
```

Add limits for repository size, file size, indexed file count, changed files,
changed lines, model turns, debugger attempts, sandbox CPU/memory/time/output,
provider timeouts, and API rate limits.

Production startup must fail when:

- secrets are missing or too short;
- secure cookies are disabled;
- legacy unauthenticated APIs are enabled;
- a writable root is unsafe;
- required provider configuration is incomplete.

### Stable error contract

Return expected failures in one shape:

```json
{
  "detail": {
    "error": {
      "code": "REPOSITORY_ACCESS_DENIED",
      "message": "You no longer have access to this repository.",
      "details": {}
    }
  }
}
```

Clients use `code`; people read `message`; `details` contains only safe bounded
context.

### Observability

Add:

- request IDs and correlation IDs;
- structured task and failure logs;
- task, stage, user, repository, plan, change-set, run, and review identifiers;
- model token, latency, and estimated-cost fields;
- sensitive-value redaction;
- a durable `TaskEvent` timeline.

Never log credentials, cookies, private keys, authorization headers, complete
issue bodies, or complete repository files.

### Phase gate

- Invalid production settings stop startup with an actionable message.
- Every response has a correlation ID.
- An expected error follows the stable error contract.
- A test proves redaction removes representative secrets.

## 5. Design the database before building routes

PostgreSQL is the source of truth. Add tables through Alembic migrations in
dependency order.

### Identity and GitHub access

| Table | Important data |
| --- | --- |
| `users` | Immutable GitHub user ID, login, name, avatar, email, active flag |
| `user_sessions` | Hashed opaque token, hashed CSRF token, expiry, revocation |
| `github_user_authorizations` | Encrypted user OAuth and refresh tokens |
| `oauth_states` | Hashed, expiring, single-use login/installation state |
| `github_installations` | User owner, GitHub installation/account IDs, status |
| `repositories` | Installation, immutable GitHub repository ID, metadata, access status |

### Task and artifacts

| Table | Important data |
| --- | --- |
| `repo_pilot_tasks` | Owner, repository, issue snapshot, state, active artifacts |
| `task_operation_locks` | Task, operation, owner, lease expiry |
| `task_events` | Ordered user-visible and operator-visible timeline |
| `agent_runs` | Role, model, timing, tokens, status, bounded metadata |
| `execution_plans` | Structured plan, file scope, approval state |
| `change_sets` | Base commit, diff, hashes, relationship to plan/run |
| `change_set_files` | Per-file before/after hashes and line counts |
| `execution_runs` | Commands, outcomes, timing, verification status |
| `debug_attempts` | Failure classification, repair attempt, child artifacts |
| `final_reviews` | Version, decision, exact diff hash, reviewer, feedback |
| `publications` | Branch, commit, pull request, retry and partial-failure state |

### Code index and evaluation

| Table | Important data |
| --- | --- |
| `repository_files` | Workspace file path, language, content hash |
| `code_symbols` | Symbol name, kind, source range |
| `code_chunks` | Searchable text, metadata, full-text vector, embedding |
| `evaluation_runs` | Suite and aggregate result |
| `evaluation_task_results` | Per-evaluation-task metrics and diagnostics |

### Required database invariants

- Identify users and repositories with immutable GitHub numeric IDs.
- Foreign-key every user-owned artifact back to a task or repository.
- Prevent more than one active task for the same user, repository, and issue.
- Version tasks for optimistic concurrency.
- Version final reviews and supersede old reviews after a new change set.
- Store OAuth and session token hashes, not raw session tokens.
- Encrypt GitHub user tokens before storage.
- Never persist short-lived GitHub installation tokens.
- Use one transaction when current state and its timeline event must agree.

### Migration order

Use migrations in this order:

1. identity, sessions, OAuth state;
2. installations and repositories;
3. tasks, locks, and events;
4. plans and model runs;
5. code index and pgvector extension;
6. change sets and verification;
7. debugging and reviews;
8. publications;
9. evaluation tables;
10. later constraints and indexes discovered by concurrency tests.

Every migration needs an upgrade, a practical downgrade, and a migration test
against a non-empty database.

### Phase gate

- A new database upgrades from zero to head.
- A representative older database upgrades without losing tasks.
- Foreign keys reject orphan artifacts.
- unique constraints reject duplicate active work.
- `pgvector` can store and query the configured embedding dimension.

## 6. Implement authentication and session security

Authentication and repository authorization are two different flows.

### GitHub login

Implement:

```text
GET /api/v1/auth/github/login
GET /api/v1/auth/github/callback
GET /api/v1/auth/me
POST /api/v1/auth/logout
```

Login sequence:

1. Generate a cryptographically random OAuth state.
2. Store only its hash with purpose, expiry, and safe redirect path.
3. Redirect to GitHub.
4. On callback, atomically consume the state.
5. Exchange the code server-side.
6. Fetch the authenticated GitHub user.
7. Upsert the local user using GitHub's numeric user ID.
8. Encrypt and store the user authorization when it is needed for
   user-attributed pull requests.
9. Create an opaque random session token.
10. Store only the session-token hash.
11. Set an HTTP-only, SameSite cookie; use Secure in production.
12. Redirect to the frontend.

### CSRF

For cookie-authenticated mutations:

1. Create a separate CSRF value.
2. Store its hash with the session.
3. Give the browser the value in a readable SameSite cookie.
4. Require the same value in `X-CSRF-Token`.
5. Compare hashes in constant time.

Do not use `localStorage` for GitHub or RepoPilot session tokens.

### Authorization helpers

Create reusable dependencies:

```text
require_auth_context
require_current_user
require_csrf
authorize_task
resolve_user_repository
```

Every tenant-scoped query must include the current user. Prefer a safe `404`
when exposing the existence of another user's object would leak information.

### Phase gate

- Login, callback, current-user, and logout tests pass.
- Expired, revoked, and malformed sessions fail.
- Replayed or expired OAuth state fails.
- A missing or incorrect CSRF header blocks mutations.
- User A cannot read any object owned by User B.

## 7. Implement GitHub App installation and repository discovery

User login answers “who is the user?” The installation answers “which
repositories can the application access?”

Implement:

```text
GET  /api/v1/auth/github/installations/setup
GET  /api/v1/auth/github/installations/callback
GET  /api/v1/github/installations
POST /api/v1/github/installations/{id}/repositories/sync
GET  /api/v1/github/repositories
GET  /api/v1/github/repositories/{repository_id}
```

### GitHub App client

The backend client must:

1. Create a short-lived JWT from App ID and private key.
2. Request a short-lived installation token.
3. List installation repositories with pagination.
4. Fetch repository metadata and permissions.
5. Fetch issues while filtering pull requests from GitHub's Issues API.
6. Map rate limits, revocation, suspension, and permission failures into stable
   application errors.

Do not store installation tokens. Mint one immediately before a GitHub
operation.

### Installation callback verification

Do not trust a callback's installation ID by itself. Verify that the signed-in
GitHub user can see the installation through GitHub's user-installation API.
Only then bind it to the local user.

### Repository synchronization

Upsert by installation ID plus immutable GitHub repository ID. Update names,
default branch, archived/disabled state, permissions, and `last_synced_at`.
Mark repositories missing from a completed synchronization as removed rather
than silently leaving them active.

Refresh the first repository page when a user returns to the selector. This
makes newly added repositories appear without reinstalling the App.

### Issue API

Implement:

```text
GET /api/v1/github/repositories/{repository_id}/issues
GET /api/v1/github/repositories/{repository_id}/issues/{issue_number}
```

Default to open issues, paginate, return labels/author/timestamps, and exclude
responses containing pull-request metadata.

### Phase gate

- Selected and all-repository installations work.
- New repositories appear after synchronization.
- Removed, suspended, and organization-approval states are visible.
- Private repository issues can be listed.
- Pull requests never appear in the normal issue selector.
- A submitted repository UUID is independently resolved through the current
  user's installation.

## 8. Build task creation and immutable issue snapshots

Implement:

```text
POST /api/v1/tasks
GET  /api/v1/tasks
GET  /api/v1/tasks/{task_id}
GET  /api/v1/tasks/{task_id}/timeline
GET  /api/v1/tasks/{task_id}/metrics
```

The create request should contain only:

```json
{
  "repository_id": "internal-repository-uuid",
  "issue_number": 142,
  "user_instructions": "Do not add dependencies."
}
```

The backend must:

1. authenticate the user and validate CSRF;
2. load the repository through the user's active installation;
3. reject archived, disabled, or removed repositories;
4. fetch the issue directly from GitHub;
5. validate bounded title, body, labels, and instructions;
6. persist the issue ID, number, title, body, URL, author, labels, and source
   timestamps;
7. derive a simple fallback issue understanding;
8. save `standard` or `strict` autonomy mode;
9. create the task in `created`;
10. append the first timeline event;
11. commit before scheduling background work;
12. return the saved task immediately.

The snapshot is important: later issue edits must not change the context that
was originally approved for the task.

### Phase gate

- Missing, unauthorized, and archived repositories fail safely.
- Missing issues fail safely.
- The database retains the issue snapshot after the GitHub issue changes.
- Two rapid create requests cannot create duplicate active tasks.
- Task listing and detail return only the signed-in user's tasks.

## 9. Implement the state machine, events, and operation locks

Create explicit states:

```text
created
repository_preparing
repository_ready
indexing
indexed
retrieving
planning
plan_pending_approval
plan_approved
plan_rejected
plan_revision_required
coding
patch_generated
testing
test_failed
debugging
verification_passed
review_pending
review_approved
review_rejected
publishing
completed
failed
cancelled
```

Create an allowed-transition map. Reject every transition not in the map. Only
`TaskService` and `TaskStateMachine` may change task state.

When appropriate, update these in one transaction:

- task status and current step;
- active artifact ID;
- task version;
- timestamps;
- one non-duplicated timeline event.

Create leased operation locks for workflow, coding, review revision, restart,
and publication. Database constraints and locks are authoritative; disabling a
frontend button is only a usability improvement.

Add cancellation checkpoints between long stages. Add a reconciler that uses
durable artifacts to repair a stale display state without inventing artifacts.

### Phase gate

- A table-driven test covers every allowed and forbidden transition.
- Concurrent operations result in one winner.
- Repeated equivalent events are not added.
- Cancellation stops at a checkpoint and records its reason.
- Reconciliation never moves a terminal task backward.

## 10. Implement isolated repository workspaces

Use a task UUID to derive:

```text
workspaces/<task-id>/repository/
```

The task must be authorized before resolving its path.

The workspace manager must:

1. create directories beneath one validated root;
2. reject absolute paths, `..`, symlink escape, and cross-workspace access;
3. clone the authorized default branch with a fresh installation token;
4. avoid placing credentials in the remote URL or process arguments;
5. record the checked-out base commit;
6. keep one workspace per task;
7. clean temporary credentials and files;
8. support intentional cleanup after retention expires.

Capture Git status, base commit, tree hash, and exact diff through deterministic
Git helpers.

### Phase gate

- Private and public repositories clone.
- Logs and `.git/config` contain no credentials.
- A task cannot resolve another task's path.
- Path traversal and symlink tests pass.
- Base commit and clean-tree state are persisted.

## 11. Build repository indexing

Index the exact checked-out commit.

### Scanner

Use `git ls-files` so ignored builds and `.git` internals are excluded. Reject
binary, unsupported, sensitive, and oversized content. Enforce total file and
byte limits.

### Parser

Use Tree-sitter for supported languages. Extract classes, functions, methods,
and source ranges. Use file-level fallback chunks when structural parsing is
unavailable.

### Persistence

Save:

- `RepositoryFile` with path, language, size, and content hash;
- `CodeSymbol` with name, kind, and line range.

Make re-indexing for one workspace idempotent.

### Phase gate

- Tracked supported files are indexed.
- ignored, binary, secret-like, and oversized files are skipped.
- parser failure for one file does not destroy the whole index.
- re-indexing does not duplicate file or symbol records.

## 12. Build the RAG pipeline

RAG supplies focused evidence instead of sending an entire repository to a
model.

### Build-time path

```text
indexed files
→ symbol-aware and fallback chunks
→ token bounds and overlap
→ embeddings
→ CodeChunk rows with pgvector and full-text data
```

### Query-time path

```text
issue snapshot + user instructions
→ bounded search query
→ structural search
→ lexical full-text search
→ semantic vector search
→ reciprocal-rank fusion
→ duplicate removal and per-file diversity
→ bounded context pack
```

Use an embedding interface so tests can provide a fake implementation. If
semantic search is temporarily unavailable, retain structural and lexical
results and record the degradation.

Do not confuse retrieval with authorization. A retrieved file is evidence; the
approved plan defines what may be changed.

### Phase gate

- Chunk boundaries and token overlap are deterministic.
- Structural, lexical, semantic, and fusion tests pass independently.
- Context limits and per-file diversity are enforced.
- An embedding outage degrades safely.
- No result points outside the current task workspace.

## 13. Implement structured planning

The planner input contains:

- repository and issue snapshot;
- optional user instructions;
- retrieved context with source paths;
- current base commit;
- security constraints;
- allowed operation rules.

Clearly label issue, repository, and user text as untrusted data.

Require structured output:

```text
summary
problem_analysis
likely_root_cause
confidence
files_to_inspect
files_to_modify or create
implementation_steps
tests
risks
assumptions
needs_more_context
missing_context
```

Validate:

- all paths are safe and repository-relative;
- modified files already exist;
- explicitly creatable files do not exist;
- source references point to valid ranges;
- limits are respected;
- implementation steps reference declared files.

Persist the plan and planner telemetry. In Standard mode, automatically approve
a structurally valid and policy-safe plan. In Strict mode, stop for human plan
approval.

Treat `needs_more_context` as a separate waiting state, not as a low-confidence
plan that a user can approve. Display `missing_context` as questions, collect a
bounded clarification, and create a new planning attempt with the original
instructions plus that answer. Keep the old task and mark its plan superseded
so the audit trail remains understandable.

Never silently widen the plan after coding begins.

### Phase gate

- Invalid model JSON cannot change state.
- Unsafe or nonexistent planned paths fail validation.
- Standard mode continues automatically.
- Strict mode stops at the plan gate.
- All planner calls create bounded telemetry records.

## 14. Implement constrained coding

The coding model must not receive an unrestricted shell or filesystem.

Expose narrow operations such as:

```text
update an existing approved file
create an explicitly approved new file
```

Before coding:

1. verify the task and approved plan;
2. verify the workspace base and expected current patch;
3. derive modifiable and creatable paths from the plan;
4. snapshot the workspace;
5. acquire the coding lock.

After coding:

1. reject paths outside plan scope;
2. reject sensitive paths and unauthorized dependency manifests;
3. reject absolute paths and symlink escapes;
4. enforce file, line, and byte limits;
5. calculate before/after file hashes;
6. calculate normalized diff hash and statistics;
7. roll back the snapshot on policy failure;
8. persist `ChangeSet` and `ChangeSetFile`;
9. transition to `patch_generated`.

If a necessary file is outside the plan, enter `plan_revision_required`.

### Phase gate

- Safe updates and creates work.
- Path traversal, symlink, secret-file, dependency, and scope attacks fail.
- Any rejected model operation leaves the workspace unchanged.
- The stored change set matches the actual Git diff.

## 15. Build Docker verification

Never run repository commands directly on the application host.

Verification must:

1. validate the change set and workspace;
2. copy the repository to a temporary sandbox directory;
3. detect Node and/or Python project metadata;
4. construct commands from known scripts and files;
5. install dependencies with limited network access;
6. run tests, typecheck, lint, and build with no network where possible;
7. apply CPU, memory, process, time, output, and filesystem limits;
8. pass only a safe environment;
9. save every command result;
10. remove the container and temporary copy.

Never mount:

- the Docker socket inside the verification container;
- the backend `.env`;
- GitHub/App/AI credentials;
- another task workspace;
- writable host directories unrelated to the sandbox.

Represent absent checks as `skipped`, not `passed`.

### Phase gate

- Node, Python, mixed, and no-test repositories are classified correctly.
- timeouts, output truncation, and resource errors are saved.
- sandbox escape regression tests pass.
- the host workspace is unchanged by verification.
- actual check results appear in `ExecutionRun`.

## 16. Implement bounded debugging

Classify failed verification before calling a debugger. Some failures are
retryable; infrastructure or policy failures may not be.

For an eligible failure:

1. create a failure fingerprint;
2. provide bounded logs, current diff, plan, and repository context;
3. allow edits only inside approved plan scope;
4. create a child change set;
5. re-run verification;
6. stop on success, no progress, repeated fingerprint, unsafe scope, timeout,
   or the configured attempt limit.

Keep the default attempt count small, such as three. Debugger output is subject
to the same path and diff policies as coder output.

### Phase gate

- A repairable fixture passes after a bounded repair.
- repeated no-progress attempts stop.
- a requested out-of-plan edit causes plan revision.
- every attempt links the parent/child artifacts and actual result.

## 17. Build exact-diff final review

Create a review only after the final execution run is acceptable.

Freeze:

- task and issue;
- plan ID and snapshot;
- final change-set ID;
- execution-run ID;
- base commit;
- normalized exact diff and hash;
- changed file list and statistics;
- actual verification results;
- debugger history;
- review version.

Implement:

```text
POST /api/v1/tasks/{task_id}/review/approve
POST /api/v1/tasks/{task_id}/review/reject
POST /api/v1/tasks/{task_id}/review/request-changes
```

Approval payloads should include expected review, change-set, and diff
identifiers. Use row locking or optimistic concurrency. A stale review returns
`409`, not success.

### Request changes

Request Changes must:

1. save bounded feedback;
2. mark the current review as superseded or changes requested;
3. invalidate any publication authorization;
4. move the task to coding;
5. run a new coder pass using the previous change set and feedback;
6. verify it;
7. create a new review version.

The new diff must be reviewed again. Feedback alone must never make the UI
pretend a new change set exists.

### Phase gate

- Approve binds the user to one exact diff.
- Reject creates no remote Git activity.
- Request Changes creates a new verified review or records an actionable
  failure.
- concurrent approve/reject/request-changes calls produce one valid result.
- a new change set invalidates old approval.

## 18. Implement deterministic publication last

Publication is normal backend code, never an AI tool.

Implement:

```text
POST /api/v1/tasks/{task_id}/publish
GET  /api/v1/publications/{publication_id}
```

Before any mutation:

1. authorize the signed-in task owner;
2. require the latest review to be approved;
3. recalculate and compare the working-tree diff hash;
4. verify the active installation and repository;
5. recheck Contents and Pull requests write permissions;
6. fetch the remote default branch and expected base SHA;
7. acquire an idempotent publication lock.

Then:

1. generate a safe collision-resistant non-default branch;
2. stage only approved paths;
3. compare the staged diff hash;
4. create a deterministic commit;
5. verify its parent and committed diff;
6. push with a fresh installation token, without force;
7. find or create the pull request with the user's OAuth token when user
   attribution is required;
8. save branch, commit, pull request, author, and timestamps;
9. transition to `completed`.

Use the installation token for repository branch access and the user's OAuth
token for user-attributed PR creation. If the product does not require user
attribution, document the App-bot identity instead of disguising it.

Persist partial progress so a retry after “push succeeded, PR failed” finds the
existing branch/commit and does not duplicate work.

Never:

- push the default branch;
- force-push;
- include unapproved files;
- publish a changed diff;
- merge the pull request.

### Phase gate

- Publication without approval fails.
- a stale diff or base fails safely.
- permission revocation fails with an actionable code.
- repeated publish requests return one publication and one PR.
- simulated PR failure resumes after the push.
- tests prove no default-branch or force push is possible.

## 19. Build the frontend in backend-capability order

Create frontend contracts only after the corresponding backend endpoint is
stable.

Use this structure:

```text
frontend/src/
├── app/                 URL routes, layouts, loading and error boundaries
├── components/          Reusable visual and feature components
├── lib/api/             Typed HTTP functions
├── lib/                 Query keys, errors, formatters, state mapping
├── providers/           TanStack Query and application providers
└── types/               Central API and UI contracts
```

The shared API client must:

- use same-origin `/api/v1` in normal browser operation;
- send cookies;
- attach request/correlation IDs;
- attach the CSRF header to mutations;
- parse the stable backend error;
- avoid retrying authentication, permission, and conflict errors aggressively.

### Frontend implementation sequence

#### A. Shell and authentication

Build:

- `/login`;
- root authentication check;
- protected application shell;
- sidebar, page header, and footer;
- sign out;
- loading, unauthenticated, backend-down, and expired-session states.

#### B. GitHub connection

Build:

- `/settings` GitHub account and installation section;
- repository-access setup button;
- installation status and repository count;
- reconnect and organization-approval messages.

#### C. Repository and issue selection

Build `/tasks/new` as:

```text
1. Repository
2. Issue
3. Understanding
4. Instructions
5. Create
```

Repository and issue lists need search, pagination, empty, error, revoked,
archived, and retry states. The first repository load should request a sync.

Also support creating an issue without leaving RepoPilot:

- require an issue title and clear description;
- list blob paths from the selected repository's default branch;
- allow up to 20 optional related-file selections;
- validate the paths again on the backend;
- create the issue with the signed-in user's GitHub App user token;
- select the new issue and continue to the Understanding step.

#### D. Task dashboard

Build `/tasks` with:

- task search and status filters;
- repository and issue identity;
- running, waiting, failed, cancelled, review, and completed states;
- changed-file and publication summaries when available.

#### E. Task detail

Build `/tasks/[taskId]` with:

- lifecycle strip;
- Overview, Plan, Changes, Verification, Debug, Timeline, and Metrics tabs;
- task actions derived from backend state;
- polling only while the status is active;
- no state mutation merely because a tab opens or closes.

#### F. Review and publication

Render the complete diff with safe horizontal scrolling and large-diff
handling. Show only actual verification results. Implement Reject, Request
Changes, Approve Final Diff, and the separate Publish Pull Request action.

After each mutation, invalidate every affected query. Disable duplicate clicks,
but rely on backend locks for correctness.

### Frontend state rule

Create one centralized mapping:

```text
backend task status
→ lifecycle stage appearance
→ available user actions
→ polling decision
```

Do not create an independent browser state machine. Two browser tabs are two
readers of the same backend state and must not stop the task.

### Phase gate

- Every page handles loading, empty, success, and error.
- no frontend bundle or network response contains secrets.
- stale-review conflicts ask the user to reload the current diff.
- polling stops or slows for terminal/waiting states.
- the UI never displays fake tests, tokens, progress, or PR data.

## 20. Add cancellation, restart, recovery, and cleanup

Implement:

```text
POST /api/v1/tasks/{task_id}/cancel
POST /api/v1/tasks/{task_id}/restart
POST /api/v1/tasks/{task_id}/reconcile
```

- Cancel sets a durable request checked between stages.
- Restart creates a safe new attempt; do not reuse an inconsistent workspace
  merely to preserve a UUID.
- A missing-context task requires a clarification payload before restart. Carry
  that answer into the new attempt and never make the user edit the GitHub issue
  just to unblock planning.
- Reconcile compares task state with durable artifacts and moves forward only
  when evidence supports it.
- Cleanup removes expired workspaces only after retention and terminal-state
  checks.

The first implementation may use FastAPI background tasks, but document that a
backend restart can interrupt active work. Before scaling to several backend
instances, move workflow and revision work into a durable queue with leases,
heartbeats, retry policy, and idempotent stage handlers.

### Phase gate

- closing or opening browser tabs does not affect workflow execution.
- a backend interruption is visible and recoverable.
- restart cannot run twice concurrently.
- cleanup cannot delete an active or another user's workspace.

## 21. Document the system while building it

Documentation is part of each milestone, not a final cleanup task. Maintain
these guides:

| Guide | Write it when |
| --- | --- |
| Product contract | Before implementation |
| Architecture and design patterns | After the skeleton and boundaries are agreed |
| Database model and migration rules | With the first migrations |
| GitHub App setup | With authentication and installation work |
| API guide | Whenever a public endpoint is added or changed |
| Task state machine and service flow | With orchestration |
| Indexing and RAG explanation | With repository intelligence |
| Frontend route and state guide | With the application shell |
| Security model | With authorization, sandbox, review, and publication |
| Testing and troubleshooting | With every stable error and recovery path |
| Deployment and backup | Before a public environment exists |

Use Mermaid for architecture, sequence, state, and entity-relationship
diagrams so the diagrams live beside the text in version control.

For every public API operation, document:

- method and path;
- authentication and CSRF requirement;
- request and response contract;
- ownership checks;
- durable state changed;
- expected error codes;
- idempotency or concurrency behavior.

For every workflow stage, document:

- entry state and allowed exit states;
- service responsible;
- external systems called;
- database artifacts created;
- timeline and log events;
- cancellation point;
- retry and recovery behavior.

Comments in source files should explain a function's local purpose or a
non-obvious invariant. They should not repeat each line of code. Markdown
guides explain cross-file behavior and operational decisions.

### Phase gate

- every implemented public route appears in the API guide;
- database and state diagrams match the current migrations and constants;
- setup steps work in a new checkout;
- no documentation example contains a real secret;
- broken local documentation links fail CI.

## 22. Add defense-in-depth tests

Do not wait until the end to add tests. Each phase must include its own tests.
Before release, run this complete matrix.

### Authentication and tenant isolation

- login/callback success and every state failure;
- logout, expiry, revocation, CSRF;
- User A cannot see or mutate User B's installation, repository, task,
  workspace, plan, diff, run, review, timeline, metrics, or publication.

### GitHub integration

- installation active/removed/suspended/approval-required;
- selected/all repositories, pagination, resync, private repository;
- issue filtering and missing issue;
- permission downgrade and rate limit.

### Workflow

- every allowed/forbidden transition;
- normal Standard and Strict paths;
- cancellation at every long stage;
- duplicate create/start/restart;
- provider failure and safe degradation;
- request changes and plan revision.

### Filesystem and sandbox

- absolute path, traversal, symlink escape;
- sensitive file and dependency policy;
- cross-workspace access;
- shell injection and unsafe environment;
- Docker limits and cleanup.

### Review and publication

- stale review, changed diff, changed base;
- concurrent decisions;
- publication without approval;
- duplicate publication;
- partial failure recovery;
- no force push, default branch push, or automatic merge.

### Frontend

- login and GitHub connection states;
- repository/issue selector states;
- task status and action mapping;
- review conflicts and request changes;
- publication success/failure;
- lint, TypeScript, unit tests, and production build.

### Evaluation

Create a fixed, versioned set of representative issues and repositories.
Measure:

- task success;
- retrieval relevance;
- plan validity;
- safe patch rate;
- verification success;
- debugger recovery;
- token usage, latency, and cost.

Never publish a benchmark result that was not actually executed.

## 23. Delivery milestones

Use these milestones for planning and team handoff:

| Milestone | Deliverable | Exit condition |
| --- | --- | --- |
| M0 | Product and security contract | Ten invariants approved |
| M1 | Project skeleton | health, frontend, DB, CI work |
| M2 | Data and shared backend foundation | migrations, config, errors, logging pass |
| M3 | Multi-user GitHub access | login, sessions, installations, repositories, issues pass |
| M4 | Task foundation | snapshot, state machine, locks, timeline, workspace pass |
| M5 | Repository intelligence | index and hybrid RAG pass |
| M6 | Agent execution | plan, constrained code, sandbox, debugger pass |
| M7 | Human control | exact review, request changes, stale conflicts pass |
| M8 | GitHub publication | idempotent safe PR creation passes |
| M9 | Complete frontend | main user journey works without manual API calls |
| M10 | Release candidate | security, regression, evaluation, backup, deployment gates pass |

Do not call M8 complete because one happy-path PR was created. The permission,
stale-state, duplicate-request, and partial-failure tests are part of the
milestone.

## 24. Recommended manual team workflow

For developers building without an AI coding assistant:

1. Turn each phase into small tickets with one acceptance gate.
2. Write the API schema and failure cases before implementing a route.
3. Add a migration and model test before writing services that depend on it.
4. Write service tests with fake GitHub, model, embedding, Git, and Docker
   adapters.
5. Implement the service.
6. Add the thin route and authorization test.
7. Add the typed frontend function.
8. Add the query/mutation and UI states.
9. Run the phase gate locally and in CI.
10. Update the relevant architecture document in the same pull request.

Good parallel work:

- visual shell while backend identity contracts stabilize;
- indexing and sandbox research after workspace contracts exist;
- test fixtures and documentation beside implementation.

Do not parallelize without an agreed contract:

- task state names and frontend status mapping;
- review versions and publication authorization;
- GitHub identity versus installation ownership;
- workspace layout and path authorization;
- plan file scope and coder/editor behavior.

## 25. Final release checklist

The application is ready for a small controlled beta only when:

- migrations upgrade a new and an existing database;
- health and readiness distinguish process and dependency health;
- secrets are absent from browser bundles, logs, Git configuration, and test
  artifacts;
- GitHub login and installation work for personal and approved organization
  accounts;
- every user-owned query applies tenant authorization;
- repository resync reflects new and removed repositories;
- one issue completes clone through review;
- Request Changes creates a genuinely new review version;
- exact-diff approval and stale-state conflicts work;
- publication is idempotent and never merges;
- backend tests pass;
- frontend lint, typecheck, unit tests, and production build pass;
- security regression tests pass;
- at least one restore from a database backup has been tested;
- operators know how to find a task by correlation and task ID;
- active workflows are drained before a backend restart.

## 26. Reference implementation map

When comparing a manual implementation with this repository, start here:

| Concern | Reference |
| --- | --- |
| Architecture and patterns | [Architecture](architecture.md) |
| Complete service sequence | [Service-Call Workflow](service-call-workflow.md) |
| State lifecycle | [Task Workflow](task-workflow.md) |
| Backend folders and responsibilities | [Backend Guide](backend-guide.md) |
| Frontend routes and state rules | [Frontend Guide](frontend-guide.md) |
| Models and transactions | [Database Guide](database-guide.md) |
| Authentication and GitHub App | [GitHub Integration](github-integration.md) |
| Indexing and retrieval | [RAG Pipeline](rag-pipeline.md) |
| Endpoint groups | [API Guide](api-guide.md) |
| Test commands and failures | [Testing and Troubleshooting](testing-and-troubleshooting.md) |
| Local environment | [Getting Started](getting-started.md) |
| Production shape | [Deployment](deployment.md) |

The reference code is organized under:

```text
backend/app/api/routes/          HTTP boundaries
backend/app/db/models/           durable data
backend/app/schemas/             request and response contracts
backend/app/services/tasks/      state, locking, workflow, recovery
backend/app/services/auth/       sessions, CSRF, authorization, user tokens
backend/app/services/github/     App JWTs, installations, repositories
backend/app/services/indexing/   tracked files and symbols
backend/app/services/retrieval/  hybrid RAG
backend/app/services/planning/   structured plan
backend/app/agents/coder/        constrained code changes
backend/app/services/sandbox/    verification
backend/app/services/debugging/  bounded correction
backend/app/services/reviews/    exact-diff human decision
backend/app/services/publishing/ deterministic GitHub publication
frontend/src/app/                routes
frontend/src/components/         user experience
frontend/src/lib/api/            typed API calls
frontend/src/lib/task-status.ts  backend-state presentation
```

Use the implementation map to verify behavior, not as a reason to bypass the
phase gates. The gates are what make the product safe and reproducible.
