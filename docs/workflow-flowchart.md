flowchart TD

%% =========================================================
%% RepoPilot — GitHub-Native AI Coding Agent
%% =========================================================

%% -------------------------
%% 1. FRONTEND
%% -------------------------
subgraph FRONT["1. Frontend"]
    direction TB

    U1["Sign in with<br/>GitHub OAuth"]
    U2["Install / configure<br/>RepoPilot GitHub App"]
    U3["Select authorized<br/>repository"]
    U4["Refresh repositories<br/>via App installation"]
    U5["Select GitHub issue<br/>+ optional instructions"]

    FE1["Next.js<br/>POST /api/v1/tasks"]
    FE2["Open task page"]
    FE3["Poll task status"]
    FE4["Click<br/>Publish Pull Request"]
end

%% -------------------------
%% 2. FASTAPI BACKEND
%% -------------------------
subgraph API["2. FastAPI backend"]
    direction TB

    A1["Receive task request"]
    A2["Validate session<br/>+ CSRF token"]
    D_AUTH{"Authentication<br/>valid?"}

    A3["Validate repository ownership<br/>App installation + issue access"]
    D_REPO{"Repository access<br/>valid?"}

    A4["TaskService.create_task()"]
    A5["Queue<br/>run_task_background()"]
    A6["Return task<br/>immediately"]
    A7["Task status API"]

    F_AUTH["Authentication Failure"]
    F_PERMISSION["GitHub Permission Denied"]
    F_BACKEND["Unexpected Backend Failure"]
end

%% -------------------------
%% 3. AI WORKFLOW
%% -------------------------
subgraph AI["3. AI workflow"]
    direction TB

    W1["TaskWorkflowService<br/>Acquire workflow lock"]
    W2["GitHubAppClient<br/>Create installation token"]

    R1["index_repository()<br/>Scan Git-tracked files"]
    R2["tree-sitter parsing<br/>Extract files + symbols"]

    R3["build_retrieval_index()<br/>Create code chunks"]
    R4["Generate embeddings"]

    R5["hybrid_search()<br/>Structural + lexical + semantic"]
    R6["Reciprocal-rank fusion<br/>Build context pack"]

    P1["PlannerService<br/>Issue + retrieved context"]
    P2["Validate generated plan"]
    D_PLAN{"Plan valid?"}
    D_MODE{"Standard or<br/>Strict mode?"}
    P3["Auto-approve<br/>valid plan"]

    C1["CodingService<br/>Issue + plan + context<br/>+ user instructions"]
    C2["Edit only files<br/>allowed by plan"]
    C3["Validate paths + patch ops<br/>diff limits + workspace"]
    D_SAFE{"Safe ChangeSet<br/>generated?"}
    D_OUTSIDE{"Needs files<br/>outside plan?"}

    E1["ExecutionService<br/>Start verification"]
    E2["Run tests + lint<br/>type checks + build"]
    D_VERIFY{"Verification<br/>passed?"}
    D_DEBUG{"Failure<br/>debuggable?"}

    DBG1["DebugOrchestrator<br/>Call debugger model"]
    DBG2["Create repaired child<br/>ChangeSet"]
    D_CONTINUE{"Continue<br/>debugging?"}

    REV1["ReviewService<br/>Create review version"]
    REV2["Bind review to<br/>base SHA + ChangeSet ID<br/>ExecutionRun ID + diff hash"]

    F_PLAN["Plan Revision Required"]
    F_PATCH["Unsafe Patch"]
    F_VERIFY["Verification Failed"]
    F_DEBUG["Debug Attempts Exhausted"]
end

%% -------------------------
%% 4. DATABASE + WORKSPACE
%% -------------------------
subgraph DATA["4. Database and workspace"]
    direction TB

    DB1[("PostgreSQL<br/>Tasks + issue snapshots")]
    WS1["Isolated task<br/>workspace"]
    WS2["Record base branch<br/>+ base commit SHA"]

    DB2[("PostgreSQL<br/>Files + symbols")]
    DB3[("PostgreSQL + pgvector<br/>Code embeddings")]

    DB4[("ChangeSet<br/>+ exact diff")]
    DB5[("ExecutionRun<br/>+ task state")]
    DB6[("Reviews + feedback<br/>Publication records")]
end

%% -------------------------
%% 5. EXTERNAL SERVICES
%% -------------------------
subgraph EXT["5. External services"]
    direction TB

    X1["GitHub OAuth"]
    X2["GitHub App<br/>+ GitHub API"]
    X3["OpenAI<br/>Embeddings model"]
    X4["OpenAI<br/>Planner model"]
    X5["OpenAI<br/>Coding model"]
    X6["OpenAI<br/>Debugger model"]
    X7["Isolated Docker<br/>sandbox"]
end

%% -------------------------
%% 6. HUMAN APPROVAL
%% -------------------------
subgraph HUMAN["6. Human approval"]
    direction TB

    H1["Wait for human<br/>plan approval"]
    H2["Human reviews<br/>final diff"]

    D_REVIEW{"Human review<br/>decision?"}

    H3["Save review feedback"]
    H4["Review Approved<br/>Publication NOT automatic"]

    F_REJECT["Review Rejected"]
end

%% -------------------------
%% 7. GITHUB PUBLICATION
%% -------------------------
subgraph PUB["7. GitHub publication"]
    direction TB

    PB1["FastAPI<br/>Handle publish request"]
    PB2["Verify App permissions<br/>repo access + OAuth<br/>review integrity"]
    D_GHPERM{"GitHub permissions<br/>valid?"}

    PB3["Read current<br/>base branch SHA"]
    D_BASE{"Base branch<br/>unchanged?"}

    PB4["PublicationService<br/>Acquire publication lock"]
    PB5["Recalculate diff hashes<br/>working tree + staged<br/>committed + approved review"]
    D_MATCH{"Approved diff<br/>still matches?"}

    PB6["SafeGitPublisher<br/>Create non-default branch"]
    PB7["Stage approved files<br/>commit + push"]
    PB8["GitHubApiPublisher<br/>Create pull request"]
    PB9["Save Publication<br/>Mark task completed"]

    SUCCESS["Pull Request Ready<br/>for Human Merge"]
    NO_MERGE["RepoPilot never<br/>automatically merges"]

    F_BASE["Base Branch Changed"]
    F_STALE["Stale State Conflict<br/>New Review Required"]
end


%% =========================================================
%% FRONTEND / AUTH FLOW
%% =========================================================

U1 --> X1
X1 --> U2
U2 --> X2
U2 --> U3
U3 --> U4
U4 -. "Installation repositories" .-> X2
U4 --> U5
U5 --> FE1

FE1 --> A1
A1 --> A2
A2 --> D_AUTH

D_AUTH -->|Yes| A3
D_AUTH -->|No| F_AUTH

A3 --> D_REPO
D_REPO -->|Yes| A4
D_REPO -->|No| F_PERMISSION

A4 --> DB1
A4 --> A5

A5 -->|Immediate response| A6
A6 --> FE2
FE2 --> FE3

FE3 --> A7
A7 -. "Read status" .-> DB1
A7 -->|Status update| FE3

A5 -->|Background| W1


%% =========================================================
%% WORKSPACE + INDEXING
%% =========================================================

W1 --> W2
W2 -. "Short-lived token" .-> X2

W2 --> WS1
WS1 -. "Clone with installation token" .-> X2

WS1 --> WS2
WS2 -. "Persist base state" .-> DB1

WS2 --> R1
R1 --> R2
R2 --> DB2

R2 --> R3
R3 --> R4
R4 -. "Embedding request" .-> X3
R4 --> DB3


%% =========================================================
%% RETRIEVAL + PLANNING
%% =========================================================

DB2 --> R5
DB3 --> R5
R5 --> R6

R6 --> P1
P1 -. "Planner request" .-> X4
P1 --> P2
P2 --> D_PLAN

D_PLAN -->|No| F_PLAN
D_PLAN -->|Yes| D_MODE

D_MODE -->|Standard| P3
P3 --> C1

D_MODE -->|Strict| H1
H1 -->|Approved| C1
H1 -->|Revision required| F_PLAN


%% =========================================================
%% CODING + CHANGESET SAFETY
%% =========================================================

C1 -. "Coding request" .-> X5
C1 --> C2
C2 --> C3
C3 --> D_SAFE

D_SAFE -->|Yes| DB4
D_SAFE -->|No| D_OUTSIDE

D_OUTSIDE -->|Yes| F_PLAN
D_OUTSIDE -->|No| F_PATCH


%% =========================================================
%% VERIFICATION + DEBUG LOOP
%% =========================================================

DB4 --> E1
E1 --> X7
X7 --> E2
E2 --> DB5
E2 --> D_VERIFY

D_VERIFY -->|Passed| REV1
D_VERIFY -->|Failed| D_DEBUG

D_DEBUG -->|No| F_VERIFY
D_DEBUG -->|Yes| DBG1

DBG1 -. "Debugger request" .-> X6
DBG1 --> DBG2
DBG2 --> DB4
DBG2 --> D_CONTINUE

D_CONTINUE -->|Retry| E1
D_CONTINUE -->|No progress| F_DEBUG
D_CONTINUE -->|Max attempts| F_DEBUG
D_CONTINUE -->|Plan revision| F_PLAN


%% =========================================================
%% REVIEW
%% =========================================================

REV1 --> REV2
REV2 --> DB6
REV2 --> H2
H2 --> D_REVIEW

D_REVIEW -->|Request Changes| H3
H3 --> DB6
H3 -->|"Retrieve context again"| R5

D_REVIEW -->|Reject| F_REJECT

D_REVIEW -->|Approved| H4
H4 --> FE4


%% =========================================================
%% EXPLICIT PUBLICATION
%% =========================================================

FE4 --> PB1
PB1 --> PB2
PB2 --> D_GHPERM

D_GHPERM -->|No| F_PERMISSION
D_GHPERM -->|Yes| PB3

PB3 -. "Read base SHA" .-> X2
PB3 --> D_BASE

D_BASE -->|No| F_BASE
D_BASE -->|Yes| PB4

PB4 --> PB5
PB5 --> D_MATCH

D_MATCH -->|No| F_STALE
D_MATCH -->|Yes| PB6

PB6 --> PB7
PB7 -. "Push with App token" .-> X2
PB7 --> PB8

PB8 -. "PR with user OAuth token" .-> X2
PB8 --> PB9

PB9 --> DB6
PB9 --> SUCCESS

SUCCESS -.-> NO_MERGE


%% =========================================================
%% UNEXPECTED FAILURE PATHS
%% =========================================================

A1 -. "Unhandled error" .-> F_BACKEND
W1 -. "Unhandled error" .-> F_BACKEND
PB1 -. "Unhandled error" .-> F_BACKEND


%% =========================================================
%% COLORS
%% =========================================================

classDef frontend fill:#DBEAFE,stroke:#2563EB,color:#0F172A,stroke-width:1.5px;
classDef backend fill:#E5E7EB,stroke:#374151,color:#111827,stroke-width:1.5px;
classDef ai fill:#EDE9FE,stroke:#7C3AED,color:#2E1065,stroke-width:1.5px;
classDef decision fill:#FFEDD5,stroke:#EA580C,color:#7C2D12,stroke-width:1.5px;
classDef success fill:#DCFCE7,stroke:#16A34A,color:#14532D,stroke-width:1.5px;
classDef failure fill:#FEE2E2,stroke:#DC2626,color:#7F1D1D,stroke-width:1.5px;
classDef system fill:#CCFBF1,stroke:#0F766E,color:#134E4A,stroke-width:1.5px;

class U1,U2,U3,U4,U5,FE1,FE2,FE3,FE4,H1,H2,H3,H4 frontend;

class A1,A2,A3,A4,A5,A6,A7,W1,W2,C3,E1,E2,REV1,REV2,PB1,PB2,PB3,PB4,PB5,PB6,PB7,PB8,PB9 backend;

class R1,R2,R3,R4,R5,R6,P1,P2,P3,C1,C2,DBG1,DBG2 ai;

class D_AUTH,D_REPO,D_PLAN,D_MODE,D_SAFE,D_OUTSIDE,D_VERIFY,D_DEBUG,D_CONTINUE,D_REVIEW,D_GHPERM,D_BASE,D_MATCH decision;

class DB1,DB2,DB3,DB4,DB5,DB6,WS1,WS2,X1,X2,X3,X4,X5,X6,X7 system;

class SUCCESS success;

class F_AUTH,F_PERMISSION,F_PLAN,F_PATCH,F_VERIFY,F_DEBUG,F_REJECT,F_BASE,F_STALE,F_BACKEND failure;

class NO_MERGE backend;


%% =========================================================
%% SUBGRAPH STYLING
%% =========================================================

style FRONT fill:#F8FAFC,stroke:#93C5FD,stroke-width:1px
style API fill:#F9FAFB,stroke:#6B7280,stroke-width:1px
style AI fill:#FAF5FF,stroke:#A78BFA,stroke-width:1px
style DATA fill:#F0FDFA,stroke:#5EEAD4,stroke-width:1px
style EXT fill:#F0FDFA,stroke:#2DD4BF,stroke-width:1px
style HUMAN fill:#F8FAFC,stroke:#60A5FA,stroke-width:1px
style PUB fill:#F9FAFB,stroke:#64748B,stroke-width:1px