# RepoPilot Frontend

Next.js App Router frontend for RepoPilot, the GitHub-native AI software
engineer agent. This application consumes the FastAPI backend, authenticates
through its HTTP-only server session, and treats backend task state as the
source of truth.

## Requirements

- Node.js 20 LTS or 22+
- RepoPilot FastAPI backend running locally

## Environment Variables

```env
NEXT_PUBLIC_REPOPILOT_API_URL=http://localhost:8000
REPOPILOT_API_URL=http://localhost:8000
NEXT_PUBLIC_REPOPILOT_CSRF_COOKIE_NAME=repopilot_csrf
```

`NEXT_PUBLIC_REPOPILOT_API_URL` is the browser-visible backend URL. `REPOPILOT_API_URL` is used by the Next.js same-origin rewrite fallback when the public variable is not set.

Do not put GitHub tokens, OpenAI API keys, database credentials, or other secrets in `NEXT_PUBLIC_*`.

## Install

```bash
npm install
```

## Run

```bash
npm run dev
```

Open http://localhost:3000.

The backend is expected at http://localhost:8000.

Sign-in and repository access require a configured GitHub App. See
[`../docs/github-app-setup.md`](../docs/github-app-setup.md).

## Build

```bash
npm run build
```

## Test

```bash
npm run lint
npm run typecheck
npm run test
```
