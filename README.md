# RepoPilot

RepoPilot is a GitHub-native AI coding agent. A user signs in with GitHub,
chooses an authorized repository and issue, and lets RepoPilot analyze the
repository, propose and implement a change, run verification, and show the
exact diff for human review. RepoPilot creates a pull request only after the
user approves that exact diff. It never merges the pull request.

## What happens during a task?

```text
GitHub issue
  → clone repository
  → index and retrieve relevant code
  → plan
  → edit an isolated workspace
  → verify in Docker
  → debug when necessary
  → human diff review
  → create branch, commit, push, and pull request
```

The application is a modular monolith:

- `frontend/` contains the Next.js user interface.
- `backend/` contains the FastAPI API, AI workflow, security checks, and
  publication logic.
- PostgreSQL stores users, tasks, events, plans, changes, reviews, and
  pgvector embeddings.
- Docker isolates repository verification commands.
- GitHub OAuth identifies users; GitHub App installations authorize
  repository access.

## Start here

New to the project? Read the documentation in this order:

1. [Beginner documentation index](docs/README.md)
2. [Build from scratch](docs/build-from-scratch.md) to recreate the product,
   or [Local setup](docs/getting-started.md) to run this repository
3. [System architecture](docs/architecture.md)
4. [Complete workflow flowchart](docs/workflow-flowchart.md)
5. [Service-call workflow](docs/service-call-workflow.md)
6. [Task workflow](docs/task-workflow.md)
7. [RAG pipeline](docs/rag-pipeline.md)

The complete documentation includes backend, frontend, authentication,
database, API, testing, troubleshooting, deployment, and a glossary.

For a low-cost public demo, see
[Free-tier deployment](docs/free-tier-deployment.md).

## Quick local start

After creating `.env` and configuring the GitHub App:

```bash
docker compose up -d postgres

cd backend
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m alembic upgrade head
python -m uvicorn app.main:app --reload --port 8000
```

In another terminal:

```bash
cd frontend
cp .env.example .env.local
npm install
npm run dev
```

Open `http://localhost:3000`. See
[Local setup](docs/getting-started.md) before running this for the first time.

## Safety rules

- GitHub and OpenAI secrets stay on the backend.
- Installation tokens are short-lived and are not stored in the database.
- Repository access is checked against the signed-in user.
- Agent code runs in a task-specific workspace.
- Verification runs in restricted Docker containers.
- The reviewed diff is hashed and rechecked before publication.
- The agent cannot push, create pull requests, or merge by itself.
- RepoPilot never force-pushes or pushes directly to the default branch.

## Useful commands

```bash
# Backend tests
cd backend
PYTHONPATH=. .venv/bin/python -m pytest -q

# Frontend checks
cd frontend
npm run lint
npm run typecheck
npm test
npm run build
```

## License

Add the project license before distributing RepoPilot publicly.
