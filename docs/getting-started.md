# Getting started

This guide runs RepoPilot locally with:

- Next.js at `http://localhost:3000`
- FastAPI at `http://localhost:8000`
- PostgreSQL with pgvector at `localhost:5432`
- Docker for PostgreSQL and repository verification

## 1. Prerequisites

Install:

- Git
- Python 3.11
- Node.js 20 LTS or 22+
- npm
- Docker Desktop or another Docker Engine
- A GitHub account
- An OpenAI API key

Docker must be running, not merely installed. Check:

```bash
git --version
python3.11 --version
node --version
npm --version
docker version
```

## 2. Understand the two GitHub connections

RepoPilot uses one GitHub App for two related jobs:

1. **GitHub OAuth** answers: "Who is this RepoPilot user?"
2. **GitHub App installation** answers: "Which repositories may RepoPilot
   access?"

The client ID and client secret support user login. The App ID and private key
let the backend mint short-lived installation tokens for repository access.
Both are required for the complete product flow.

Follow [GitHub App setup](github-app-setup.md) before trying to sign in.

## 3. Create backend environment variables

From the repository root:

```bash
cp .env.example .env
```

Edit `.env` and set real values:

```env
APP_ENV=development
APP_BASE_URL=http://localhost:8000
FRONTEND_URL=http://localhost:3000
SESSION_SECRET=replace-with-at-least-32-random-characters
COOKIE_SECURE=false
ALLOW_LEGACY_UNAUTHENTICATED_API=true

GITHUB_APP_ID=123456
GITHUB_APP_PRIVATE_KEY_PATH=/absolute/path/to/repopilot.private-key.pem
GITHUB_APP_CLIENT_ID=Iv1.example
GITHUB_APP_CLIENT_SECRET=replace-me
GITHUB_APP_SLUG=your-github-app-slug
GITHUB_USER_TOKEN_ENCRYPTION_SECRET=use-a-different-32-character-secret

OPENAI_API_KEY=replace-me
DATABASE_URL=postgresql+asyncpg://repopilot:repopilot@localhost:5432/repopilot
```

Prefer `GITHUB_APP_PRIVATE_KEY_PATH` locally because it avoids multiline `.env`
formatting errors. Never commit `.env`, the PEM file, or any token.

Generate independent development secrets, for example:

```bash
openssl rand -hex 32
```

Run that command twice. Use one value for `SESSION_SECRET` and another for
`GITHUB_USER_TOKEN_ENCRYPTION_SECRET`.

## 4. Create frontend environment variables

```bash
cp frontend/.env.example frontend/.env.local
```

The local values are:

```env
NEXT_PUBLIC_REPOPILOT_API_URL=http://localhost:8000
REPOPILOT_API_URL=http://localhost:8000
```

Only browser-safe values may use the `NEXT_PUBLIC_` prefix. Never put GitHub,
OpenAI, database, or encryption secrets there.

## 5. Start PostgreSQL

From the repository root:

```bash
docker compose up -d postgres
docker compose ps
```

The image includes PostgreSQL and the pgvector extension used for semantic
code retrieval.

## 6. Install and start the backend

```bash
cd backend
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
python -m alembic upgrade head
python -m uvicorn app.main:app --reload --port 8000
```

Keep this terminal open. Useful URLs:

- Health: `http://localhost:8000/health`
- Readiness: `http://localhost:8000/ready`
- Interactive API: `http://localhost:8000/docs`

`/health` only proves that FastAPI is running. `/ready` also checks the
database, configuration, writable directories, and Docker.

## 7. Install and start the frontend

In a second terminal:

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:3000`.

## 8. Create the first task

1. Select **Continue with GitHub**.
2. Select **Configure GitHub Access**.
3. Install the GitHub App on all repositories or selected repositories.
4. Return to RepoPilot.
5. Select a repository.
6. Select an open issue.
7. Review RepoPilot's understanding and add optional instructions.
8. Create the task.
9. Wait for planning, coding, verification, and final review.
10. Review the exact diff.
11. Approve it, then select **Publish Pull Request**.

Opening the task in another browser tab does not intentionally stop it. The
workflow runs in the backend process. Stopping or restarting the backend can
interrupt an in-process task; see [Task workflow](task-workflow.md).

## 9. Stop the application

Stop the frontend and backend with `Ctrl+C`. Stop PostgreSQL with:

```bash
docker compose stop postgres
```

Your database remains in the `postgres_data` Docker volume.

Do not run `docker compose down -v` unless you intentionally want to delete the
local database.

## Next steps

- Read [Architecture](architecture.md) for the big picture.
- Read [GitHub integration](github-integration.md) if login or repository
  access is confusing.
- Read [Testing and troubleshooting](testing-and-troubleshooting.md) if
  readiness fails.
