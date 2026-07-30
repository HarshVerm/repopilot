# Service-Call Workflow

This guide shows which RepoPilot service calls which other service, and when.
Read [Task Workflow](task-workflow.md) first if the task stages are unfamiliar.

## The shortest possible explanation

```mermaid
flowchart LR
    U[User in Next.js] --> A[FastAPI route]
    A --> T[TaskService saves task]
    A -. queues .-> W[TaskWorkflowService]
    W --> C[Clone]
    W --> I[Index]
    W --> R[RAG retrieval]
    W --> P[Planner]
    W --> E[Coder]
    W --> V[Docker verification]
    V -->|failed and retryable| D[Debugger]
    D --> V
    V -->|passed| H[Final review]
    H -->|request changes| E
    H -->|approve| B[Wait for Publish click]
    B --> X[PublicationService]
    X --> G[GitHub branch and pull request]
```

The browser starts operations and displays saved state. It does not run the AI
workflow.

## Main service map

```mermaid
flowchart TD
    subgraph Frontend["Next.js frontend"]
        UI[React components]
        Q[TanStack Query]
        FC[Typed API client]
        UI --> Q --> FC
    end

    subgraph Routes["FastAPI route layer"]
        TR[tasks routes]
        RR[reviews routes]
        PR[publishing routes]
        AR[auth and GitHub routes]
    end

    subgraph Shared["Shared security and state services"]
        AUTH[Auth and authorization services]
        TS[TaskService]
        LOCK[TaskOperationLockService]
        DB[(PostgreSQL)]
        AUTH --> DB
        TS --> DB
        LOCK --> DB
    end

    subgraph Workflow["Background task workflow"]
        TW[TaskWorkflowService]
        WM[WorkspaceManager]
        IDX[index_repository]
        RAG[Retrieval services]
        PLAN[PlannerService]
        CODE[CodingService]
        EXEC[ExecutionService]
        DEBUG[DebugOrchestrator]
        REVIEW[ReviewService]
        TW --> WM
        TW --> IDX
        TW --> RAG
        TW --> PLAN
        TW --> CODE
        TW --> EXEC
        TW --> DEBUG
        TW --> REVIEW
    end

    subgraph External["External or isolated systems"]
        GH[GitHub API]
        AI[OpenAI models]
        DOCKER[Docker sandbox]
        GIT[Local Git workspace]
    end

    subgraph Publication["User-triggered publication"]
        PUB[PublicationService]
        SAFE[SafeGitPublisher]
        GHPR[GitHubApiPublisher]
        PUB --> SAFE
        PUB --> GHPR
    end

    FC --> TR
    FC --> RR
    FC --> PR
    FC --> AR
    TR --> AUTH
    RR --> AUTH
    PR --> AUTH
    AR --> AUTH
    TR --> TS
    TR -. FastAPI BackgroundTasks .-> TW
    RR --> REVIEW
    RR -. revision BackgroundTask .-> TW
    PR --> PUB
    TW --> TS
    TW --> LOCK
    WM --> GIT
    IDX --> DB
    RAG --> DB
    RAG --> AI
    PLAN --> AI
    PLAN --> DB
    CODE --> AI
    CODE --> GIT
    CODE --> DB
    EXEC --> DOCKER
    EXEC --> DB
    DEBUG --> AI
    DEBUG --> EXEC
    REVIEW --> GIT
    REVIEW --> DB
    PUB --> DB
    SAFE --> GIT
    SAFE --> GH
    GHPR --> GH
```

Solid arrows represent direct calls. Dotted arrows show work queued to run after
the API operation has created or updated durable state.

## 1. Create Task: browser request

The browser request does only the setup work required to safely start a task.
It does not wait for planning or coding.

```mermaid
sequenceDiagram
    autonumber
    actor User
    participant UI as CreateTaskModal
    participant API as tasks.create_task route
    participant Auth as Auth/CSRF services
    participant Repo as Repository authorization
    participant GH as GitHubAppClient
    participant Task as TaskService
    participant DB as PostgreSQL
    participant BG as FastAPI BackgroundTasks

    User->>UI: Select repository, issue, and Create Task
    UI->>API: POST /api/v1/tasks
    API->>Auth: Require session and validate CSRF
    API->>Repo: resolve_user_repository
    Repo->>DB: Load installation and repository for user
    API->>GH: get_issue
    GH-->>API: Current issue snapshot
    API->>Task: create_task
    Task->>DB: Insert RepoPilotTask
    API->>Task: record_event(issue.snapshot.persisted)
    Task->>DB: Insert TaskEvent
    API->>BG: add_task(run_task_background)
    API-->>UI: Return saved task immediately
    UI-->>User: Navigate to task detail
```

Important code:

| Step | Code |
| --- | --- |
| Frontend call | `frontend/src/lib/api/tasks.ts` → `createTask()` |
| HTTP route | `backend/app/api/routes/tasks.py` → `create_task()` |
| Repository ownership | `resolve_user_repository()` |
| Issue fetch | `GitHubAppClient.get_issue()` |
| Durable task record | `TaskService.create_task()` |
| Background entry point | `run_task_background()` |

## 2. Background workflow: repository to review

`run_task_background()` creates `TaskWorkflowService` and calls `run_task()`.
The workflow lock prevents duplicate starts for the same task.

```mermaid
sequenceDiagram
    autonumber
    participant BG as run_task_background
    participant WF as TaskWorkflowService
    participant Task as TaskService / locks
    participant GH as GitHubAppClient
    participant Work as WorkspaceManager
    participant Index as Indexing services
    participant RAG as Retrieval services
    participant Plan as PlannerService
    participant Code as CodingService
    participant Test as ExecutionService
    participant Debug as DebugOrchestrator
    participant Review as ReviewService

    BG->>WF: run_task(task_id)
    WF->>Task: Acquire workflow lock
    WF->>Task: created → repository_preparing
    WF->>GH: create_installation_token
    WF->>Work: clone_repository
    WF->>Task: Save workspace and base commit
    WF->>Index: index_repository
    WF->>RAG: build_retrieval_index
    WF->>RAG: hybrid_search(issue text)
    WF->>Plan: create_plan
    Plan-->>WF: Approved plan or plan gate
    WF->>Code: implement_plan
    Code-->>WF: Generated change set
    WF->>Test: execute_change_set
    alt Verification passed
        Test-->>WF: Passed execution run
    else Failed and eligible for repair
        Test-->>WF: Failed execution run
        WF->>Debug: debug_execution_run
        loop Until passed or retry policy stops
            Debug->>Test: execute repaired change set
            Test-->>Debug: Retry execution run
        end
        Debug-->>WF: Final change set and run
    else Failure is not repairable
        Test-->>WF: Stop with classified failure
    end
    WF->>Review: create_review
    Review->>Task: Transition to review_pending
```

### Exact service order

| Order | Service or function | What it does | Main dependency |
| --- | --- | --- | --- |
| 1 | `TaskOperationLockService.acquire()` | Stops duplicate workflow starts | PostgreSQL |
| 2 | `TaskService.transition_task()` | Saves `repository_preparing` and timeline event | PostgreSQL |
| 3 | `GitHubAppClient.create_installation_token()` | Gets short-lived repository credentials | GitHub |
| 4 | `WorkspaceManager.clone_repository()` | Shallow-clones the default branch | Git and GitHub |
| 5 | `TaskService.attach_workspace()` | Connects the task to its workspace | PostgreSQL |
| 6 | `index_repository()` | Scans tracked files and extracts symbols | Workspace and PostgreSQL |
| 7 | `build_retrieval_index()` | Creates code chunks and embeddings | OpenAI and PostgreSQL/pgvector |
| 8 | `hybrid_search()` | Runs structural, lexical, and semantic search, then fuses results | PostgreSQL and OpenAI |
| 9 | `PlannerService.create_plan()` | Builds, runs, validates, and stores a structured plan | Planner model and PostgreSQL |
| 10 | `CodingService.implement_plan()` | Runs the coder inside an approved file boundary and stores the exact diff | Coder model, workspace, PostgreSQL |
| 11 | `ExecutionService.execute_change_set()` | Detects project commands and runs them in Docker | Docker and PostgreSQL |
| 12 | `classify_execution_run()` | Decides whether a failed run is debuggable | Saved execution result |
| 13 | `DebugOrchestrator.debug_execution_run()` | Runs bounded repair attempts and retests child change sets | Debugger model, Docker, PostgreSQL |
| 14 | `ReviewService.create_review()` | Rechecks the final workspace and binds the review to an exact diff hash | Git workspace and PostgreSQL |

## Inside the major stages

### Indexing

```mermaid
flowchart LR
    IR[index_repository] --> SC[scan_repository]
    SC --> GL[git ls-files]
    IR --> PS[parse_source]
    PS --> TS[tree-sitter]
    IR --> ES[extract_symbols]
    IR --> DB[(RepositoryFile and CodeSymbol)]
```

### RAG retrieval

```mermaid
flowchart LR
    B[build_retrieval_index] --> CH[Chunking service]
    CH --> EM[OpenAIEmbeddingClient]
    EM --> DB[(CodeChunk + pgvector)]
    Q[Issue title and body] --> HS[hybrid_search]
    HS --> ST[Structural retrieval]
    HS --> LX[Lexical retrieval]
    HS --> SE[Semantic retrieval]
    ST --> RF[Reciprocal-rank fusion]
    LX --> RF
    SE --> RF
    RF --> CP[Context pack]
    CP --> PL[Planner]
    CP --> CO[Coder]
```

### Planning

`PlannerService.create_plan()`:

1. moves the task to `planning`;
2. creates a planner `AgentRun`;
3. calls `build_planner_input()`;
4. calls `AgentsPlannerRunner.run()` to use the configured model;
5. validates the structured `PlannerOutput`;
6. stores `ExecutionPlan`;
7. moves to `plan_pending_approval`;
8. auto-approves in Standard mode, or waits in Strict mode.

### Coding

`CodingService.implement_plan()`:

1. requires an approved plan;
2. validates a clean or expected revision workspace;
3. derives allowed and creatable files from the plan;
4. acquires the coding lock;
5. creates a coder `AgentRun`;
6. calls `AgentsCoderRunner.run()` with `RepoPilotPatchEditor`;
7. validates changed paths and diff limits;
8. rolls back unsafe output;
9. stores `ChangeSet` and `ChangeSetFile` records;
10. moves the task to `patch_generated`.

The model never receives unrestricted filesystem write access. The patch editor
and post-run validators enforce the approved file scope.

### Verification and debugging

`ExecutionService.execute_change_set()` validates workspace consistency, creates
an `ExecutionRun`, prepares `DockerSandbox`, detects the project, builds a
command plan, runs bounded commands, saves results, and cleans up the container.

If a failure is eligible, `DebugOrchestrator` calls the debugger model, validates
the repaired patch against the approved plan, creates a child change set, and
calls `ExecutionService` again. It stops on success, a non-retryable failure, no
progress, plan revision, or the configured attempt limit.

## 3. Human review actions

### Approve

```mermaid
sequenceDiagram
    actor User
    participant UI as FinalReview component
    participant API as reviews route
    participant Auth as Authorization and CSRF
    participant Review as ReviewService
    participant Git as Workspace Git checks
    participant Task as TaskService
    participant DB as PostgreSQL

    User->>UI: Approve Final Diff
    UI->>API: POST /tasks/{id}/review/approve
    API->>Auth: Authorize task and validate CSRF
    API->>Review: approve_review with expected IDs and hash
    Review->>DB: Lock and load active review
    Review->>Git: revalidate_review_integrity
    Git-->>Review: Current diff matches reviewed diff
    Review->>DB: Save approved decision
    Review->>Task: review_pending → review_approved
    API-->>UI: Approved review
```

Approval does not publish. It only records that one exact diff may be published.

### Request changes

```mermaid
sequenceDiagram
    actor User
    participant UI as FinalReview component
    participant API as reviews route
    participant Review as ReviewService
    participant Task as TaskService
    participant BG as run_revision_background
    participant RAG as hybrid_search
    participant Code as CodingService
    participant Test as ExecutionService
    participant NewReview as ReviewService.create_review

    User->>UI: Enter feedback and Request Changes
    UI->>API: POST /tasks/{id}/review/request-changes
    API->>Review: request_changes
    Review->>Task: review_pending → coding
    API->>BG: Queue revision with old change-set ID and feedback
    API-->>UI: Changes requested
    BG->>RAG: Refresh issue-relevant context
    BG->>Code: implement_plan(previous change set, feedback)
    Code->>Test: Verify new change set
    Test-->>BG: Passed or failed
    BG->>NewReview: Create a new review version when passed
```

The revision must materially change the diff. If feedback requires a file
outside the approved plan, coding stops with plan revision required.

## 4. Publish Pull Request

Publication is a separate request because it changes GitHub externally.

```mermaid
sequenceDiagram
    autonumber
    actor User
    participant UI as FinalReview component
    participant API as publishing.publish_task
    participant Auth as native_publication_context
    participant GHApp as GitHubAppClient
    participant UserToken as GitHubUserTokenService
    participant Pub as PublicationService
    participant Review as ReviewService
    participant Git as SafeGitPublisher
    participant GH as GitHubApiPublisher
    participant Task as TaskService
    participant DB as PostgreSQL

    User->>UI: Publish Pull Request
    UI->>API: POST /tasks/{id}/publish
    API->>Auth: Authorize task and validate CSRF
    Auth->>GHApp: Verify installation, repository, permissions, and base SHA
    Auth->>UserToken: Load or refresh encrypted user OAuth token
    API->>Pub: publish_review
    Pub->>Review: Validate approved review and final change set
    Pub->>DB: Acquire publishing lock and save Publication
    Pub->>Review: Revalidate current workspace diff
    Pub->>Git: Create safe non-default branch
    Pub->>Git: Stage only approved paths
    Pub->>Git: Compare staged diff hash
    Pub->>Git: Commit and verify parent plus committed diff
    Pub->>Git: Push using installation token
    Pub->>GH: Find or create PR using user OAuth token
    GH-->>Pub: Pull request number, URL, and author
    Pub->>DB: Save published result
    Pub->>Task: publishing → completed
    API-->>UI: Publication response
```

Two credentials are intentionally used:

- the GitHub App installation token pushes the authorized repository branch;
- the signed-in user's OAuth token creates the pull request so GitHub shows the
  user as the PR creator.

`PublicationService` rechecks the diff at the working-tree, staged, committed,
and remote-branch boundaries. Any mismatch stops publication.

## 5. Cancel, Restart, and Reconcile

| User action | Route | Calls | Result |
| --- | --- | --- | --- |
| Cancel | `POST /tasks/{id}/cancel` | authorization → CSRF → `TaskService.request_cancel()` | Saves the cancellation request; workflow cancellation checkpoints stop safely |
| Restart | `POST /tasks/{id}/restart` | authorization → repository resolution → `GitHubAppClient.get_issue()` → `TaskService.create_task()` → `run_task_background()` | Creates a new task linked by timeline events; it does not reuse a corrupted run |
| Reconcile | `POST /tasks/{id}/reconcile` | authorization → CSRF → `TaskReconciler.reconcile_task()` | Aligns saved status with durable artifacts when safe |
| Refresh page | `GET /tasks/{id}` and related queries | typed frontend clients → read routes → services/DB | Reads state only; it does not start or stop workflow work |

## Where each output is saved

| Output | Database record or location |
| --- | --- |
| Signed-in identity | `User`, `UserSession` |
| Repository access | `GitHubInstallation`, `Repository` |
| Current task status | `RepoPilotTask` |
| Timeline | `TaskEvent` |
| Clone and edits | `workspaces/<task-id>/repository` |
| Indexed files and symbols | `RepositoryFile`, `CodeSymbol` |
| RAG chunks and embeddings | `CodeChunk` |
| AI call telemetry | `AgentRun` |
| Plan | `ExecutionPlan` |
| Proposed diff | `ChangeSet`, `ChangeSetFile` |
| Verification | `ExecutionRun` |
| Repair history | `DebugAttempt` |
| Human approval | `FinalReview` |
| Branch and PR result | `Publication` |

## How the UI stays updated

The task detail page uses TanStack Query to call:

- `getTask()`;
- `getTaskTimeline()`;
- `getTaskMetrics()`;
- the plan, diff, review, execution, and publication readers when IDs exist.

While the task is active, the main task query polls about every three seconds.
Each browser tab is only another reader. Backend services continue independently
unless the backend process itself stops.

## Source files to follow while debugging

| Concern | Primary file |
| --- | --- |
| Create, cancel, restart, reconcile routes | `backend/app/api/routes/tasks.py` |
| Main background orchestration | `backend/app/services/tasks/workflow.py` |
| Task state and events | `backend/app/services/tasks/service.py` |
| Allowed state transitions | `backend/app/services/tasks/state_machine.py` |
| Repository clone | `backend/app/services/workspace/manager.py` |
| File and symbol index | `backend/app/services/indexing/indexer.py` |
| RAG build and search | `backend/app/services/retrieval/service.py` |
| Planning | `backend/app/services/planning/service.py` |
| Coding | `backend/app/agents/coder/service.py` |
| Verification | `backend/app/services/sandbox/manager.py` |
| Debug repair loop | `backend/app/services/debugging/orchestrator.py` |
| Final review and feedback | `backend/app/services/reviews/service.py` |
| Publication route and credentials | `backend/app/api/routes/publishing.py` |
| Publication integrity and GitHub calls | `backend/app/services/publishing/service.py` |
| Frontend task requests | `frontend/src/lib/api/tasks.ts` |
| Frontend review requests | `frontend/src/lib/api/reviews.ts` |
| Frontend publication requests | `frontend/src/lib/api/publications.ts` |

