# RepoPilot documentation

This documentation explains RepoPilot from a beginner's point of view. You do
not need to understand AI agents, OAuth, FastAPI, Next.js, or vector databases
before starting.

## Recommended reading order

| Guide | What you will learn |
| --- | --- |
| [Getting started](getting-started.md) | Install dependencies, configure environment variables, and run the application |
| [Architecture](architecture.md) | Understand the major components and how a request travels through the system |
| [Complete workflow flowchart](workflow-flowchart.md) | View the entire task and service lifecycle in one diagram |
| [Service-call workflow](service-call-workflow.md) | See which route and service calls next from task creation through publication |
| [Backend guide](backend-guide.md) | Find API routes, services, models, agents, security, and observability code |
| [Frontend guide](frontend-guide.md) | Understand routes, components, API calls, queries, and UI state |
| [GitHub integration](github-integration.md) | Understand login, installations, repository permissions, and pull-request identity |
| [Task workflow](task-workflow.md) | Follow a task from issue selection to pull-request publication |
| [RAG pipeline](rag-pipeline.md) | Understand how RepoPilot finds relevant repository code |
| [Database guide](database-guide.md) | Understand tables, relationships, migrations, and local reset procedures |
| [API guide](api-guide.md) | See every API group and its purpose |
| [Testing and troubleshooting](testing-and-troubleshooting.md) | Run checks and diagnose common errors |
| [Deployment](deployment.md) | Deploy the current architecture safely |
| [Glossary](glossary.md) | Look up unfamiliar words and abbreviations |

## Existing advanced references

These pages contain lower-level implementation or migration details:

- [GitHub App setup](github-app-setup.md)
- [GitHub-native architecture change](github-native-architecture.md)
- [Frontend/API gap report](frontend-api-gaps.md)
- [Evaluation framework](../backend/docs/evaluation.md)

## Project map

```text
repopilot/
├── backend/
│   ├── app/                 FastAPI application and workflow code
│   ├── migrations/          Alembic database migrations
│   ├── tests/               Backend automated tests
│   ├── evals/               AI quality evaluation fixtures and reports
│   └── scripts/             Command-line utilities
├── frontend/
│   ├── src/app/             Next.js routes
│   ├── src/components/      User-interface components
│   ├── src/lib/             API clients and frontend utilities
│   └── src/types/           Shared TypeScript types
├── docs/                    Project documentation
├── workspaces/              Local task-specific repository clones
├── .env.example             Backend environment template
└── docker-compose.yml       Local PostgreSQL/pgvector service
```

`workspaces/`, `.env`, `.env.local`, virtual environments, dependencies, and
build outputs must not be committed.

## Where should I make a change?

| Goal | Start here |
| --- | --- |
| Add or change an HTTP endpoint | `backend/app/api/routes/` |
| Change business behavior | `backend/app/services/` |
| Change task lifecycle rules | `backend/app/services/tasks/` |
| Trace which service runs next | [Service-call workflow](service-call-workflow.md) |
| Change AI planner/coder/debugger behavior | `backend/app/agents/` and `backend/app/services/planning/` |
| Change database storage | `backend/app/db/models/` plus a migration |
| Change a page | `frontend/src/app/` |
| Change reusable UI | `frontend/src/components/` |
| Change browser API calls | `frontend/src/lib/api/` |
| Change frontend task-state display | `frontend/src/lib/task-status.ts` |

## Documentation rule

When behavior changes, update the related guide in the same change. Code
comments explain a class or function locally; these Markdown guides explain
how the parts work together.
