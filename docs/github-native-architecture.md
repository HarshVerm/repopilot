# RepoPilot GitHub-Native Architecture Change

## Existing architecture

RepoPilot is a FastAPI and SQLAlchemy Async application with an Alembic-managed
PostgreSQL/pgvector schema. Its task state is authoritative in
`RepoPilotTask`, with timeline and metrics data persisted separately. Existing
services already provide repository workspaces, tree-sitter indexing, hybrid
retrieval, structured planning, secure coding, Docker verification, bounded
debugging, exact-diff final review, idempotent Git publication, evaluation, and
crash reconciliation.

The Next.js App Router frontend uses TypeScript, Tailwind CSS, and TanStack
Query. It consumes `/api/v1` and maps backend task states into human-readable
presentation states without mutating lifecycle state locally.

Before this change GitHub access was based on one server token, task creation
accepted a caller-provided `owner/repo`, and API resources had no user/tenant
ownership.

## Change boundary

The agent domain remains unchanged:

```text
workspace → index → retrieve → plan → code → verify → debug → changeset
```

The new application and publication boundary is:

```text
authenticated user
  → active GitHub App installation
    → synchronized accessible repository
      → validated GitHub issue snapshot
        → owned RepoPilot task
          → exact-diff final review
            → deterministic publication service
```

GitHub OAuth establishes user identity. GitHub App installations establish
repository authority. OAuth tokens and installation tokens are never exposed
to browser JavaScript or persisted as long-lived installation credentials.
Installation tokens are minted server-side for the specific installation when
GitHub access is required.

The installation setup callback is not trusted on its numeric installation ID
alone. RepoPilot follows it with a user-bound OAuth verification and activates
the installation only when GitHub's `/user/installations` response confirms
that the authenticated numeric GitHub user can access it.

Sessions are opaque, server-side, expiring database records addressed by an
HTTP-only cookie. OAuth state is single-use and server-side. Mutating
cookie-authenticated requests require a same-origin CSRF header/cookie pair.

## Reused services

- `WorkspaceManager` remains responsible for isolated clones.
- Indexing, retrieval, planner, coder, sandbox, and debugger services are kept
  as the agent execution domain.
- `TaskService` and `TaskStateMachine` remain the only lifecycle mutation
  boundary.
- `ReviewService` continues to freeze the final changeset and hash its exact
  diff.
- `PublishingService` continues to revalidate the diff, base commit, staging,
  commit parent, remote branch, and pull-request state.
- Existing task locking, cancellation, reconciliation, observability,
  security regression, and evaluation systems remain in place.

## Compatibility strategy

Existing owner/repository task fields and strict plan approval routes remain so
evaluation fixtures and administrative workflows continue to work. New
GitHub-native tasks use an internal repository ID, persist a bounded issue
snapshot, default to Standard autonomy, and are tenant-scoped. Legacy
unauthenticated development APIs are available only when explicitly enabled;
production configuration rejects them.

Existing task ownership is introduced as nullable so current databases can be
migrated without assigning an arbitrary production user. Such records are
legacy administrative data and are not exposed through authenticated tenant
queries.

## Security invariants

- A repository ID is resolved through the current user's active installation.
- A task-scoped resource is accessible only when its task belongs to the
  current user.
- Workspace paths are derived from authorized task records, never directly
  from caller identity data.
- Issue content and optional instructions are persisted as untrusted context;
  they do not widen the planner/coder modification policy.
- Any new changeset supersedes prior review approval.
- Publication requires an approved review owned by the current user and an
  exact current diff hash match.
- Publication uses a fresh installation token and never pushes the default
  branch, force-pushes, or merges a pull request.

Developer setup is documented in
[`github-app-setup.md`](./github-app-setup.md).
