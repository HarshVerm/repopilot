# Testing and Troubleshooting

Start with the smallest check that can explain the problem, then expand. A
browser message such as "Internal Server Error" is only a summary; the backend
log normally contains the real cause.

## Run all backend tests

From `backend/`:

```bash
PYTHONPATH=. .venv/bin/python -m pytest -q
```

## Run all frontend checks

From `frontend/`:

```bash
npm run lint
npm run typecheck
npm test
npm run build
```

The production build matters even when lint and unit tests pass because Next.js
performs additional route and rendering checks.

## What each test layer catches

| Check | Best at catching |
| --- | --- |
| Backend unit tests | Service rules, state transitions, parsing, and helpers |
| Backend integration tests | Database, route, and service behavior together |
| Frontend unit tests | Component and hook behavior |
| ESLint | Suspicious or inconsistent JavaScript/TypeScript |
| TypeScript | Incorrect request, response, prop, and state shapes |
| Next.js build | Production routing and rendering problems |
| Evaluation runs | End-to-end agent quality across representative tasks |

See [Evaluation Guide](../backend/docs/evaluation.md) for evaluation-specific
instructions.

## Read the backend logs

Run the backend in a visible terminal:

```bash
cd backend
source .venv/bin/activate
python -m uvicorn app.main:app --reload --port 8000
```

Set `TASK_LOG_LEVEL=DEBUG` locally when more task detail is needed. Return it to
`INFO` after diagnosis to avoid excessive output.

Useful log context includes:

- task ID;
- user ID;
- repository ID;
- operation and workflow stage;
- state before and after a transition;
- plan, change-set, execution-run, and review IDs;
- exception type and stack trace.

Logs must never contain tokens, cookies, authorization headers, private keys, or
unencrypted secrets.

## Basic dependency checks

```bash
docker compose ps
curl http://localhost:8000/health
curl http://localhost:8000/ready
```

If health works but readiness fails, inspect PostgreSQL, migrations, and required
configuration.

## A task looks stuck

1. Open the **Timeline** tab and note the last saved event.
2. Open the **Debug** or failure diagnostics section.
3. Find the task ID in backend logs.
4. Confirm the backend process is still the same process that started the task.
5. Check PostgreSQL and Docker availability.
6. Use **Reconcile** if durable artifacts exist but the displayed state is
   stale.
7. Use **Restart** only when the task reports a recoverable state.

Opening the same task in a second browser tab does not stop it. Restarting the
backend can interrupt it because the current workflow runner is process-local.

## Common errors

### `GITHUB_AUTH_NOT_CONFIGURED`

Meaning: OAuth login credentials were not loaded.

Check:

- `GITHUB_APP_CLIENT_ID`;
- `GITHUB_APP_CLIENT_SECRET`;
- the backend is reading the intended `.env`;
- the values contain no accidental quotes or spaces;
- the backend was restarted after the change.

### `GITHUB_APP_NOT_CONFIGURED`

Meaning: repository installation access is incomplete.

Check:

- `GITHUB_APP_ID`;
- `GITHUB_APP_SLUG`;
- client ID and client secret;
- `GITHUB_APP_PRIVATE_KEY` or `GITHUB_APP_PRIVATE_KEY_PATH`;
- escaped `\n` characters in an inline private key are converted correctly;
- the key belongs to the same GitHub App.

### OAuth callback shows `Internal Server Error`

Check the backend traceback first. Then verify:

- GitHub callback URL exactly matches
  `http://localhost:8000/api/v1/auth/github/callback`;
- OAuth state was not reused or allowed to expire;
- PostgreSQL is reachable and migrations are current;
- client secret is correct;
- the frontend and backend URLs use the same hostname style consistently
  (`localhost` rather than mixing it with `127.0.0.1`).

### Repository is missing

If the GitHub App installation uses **Only select repositories**, add the new
repository to the existing installation on GitHub. Then revisit the first
repository page or trigger installation sync.

If it uses **All repositories**, confirm the repository belongs to the account
where the App is installed, then refresh.

### Creating a task returns 500

Inspect the response body and backend traceback. Check:

- selected repository still belongs to the current user installation;
- issue still exists and is accessible;
- task tables are migrated;
- required OpenAI and GitHub configuration is loaded;
- background workflow creation did not fail before returning.

### `PlanRevisionRequired`

The coder needs to create or modify a file outside the approved plan scope. This
is a safety result, not a browser timeout. Revise the plan so it explicitly
allows the required file.

### `WorkspaceStateMismatchError`

The task's working tree no longer matches its expected base or saved artifacts.
Possible causes include:

- two workflow operations wrote to one workspace;
- a previous run stopped midway;
- a file changed after the approved diff was created;
- workspace files were manually edited.

Use the timeline and structured workspace logs. Reconcile or restart through the
application; do not manually change the database status.

### `sandbox_error`

Check:

- Docker daemon is running;
- the configured sandbox image exists;
- the backend can access the Docker socket;
- command limits and mounted paths are valid;
- repository verification commands exist.

Docker access is highly privileged. Do not solve the error by broadly exposing
the Docker socket to untrusted services.

### `GITHUB_PERMISSION_DENIED` while publishing

RepoPilot needs:

- Contents: read and write;
- Pull requests: read and write.

After changing GitHub App permissions, approve the updated permissions for the
existing installation. Also confirm that the specific repository is included.

### Stale state conflict during publication

The working-tree diff differs from the exact diff approved by the user. Return
to final review and approve the current diff. Do not bypass the hash check.

### Request Changes saves feedback but no new diff appears

1. Confirm the request returned success.
2. Confirm a new timeline event contains the feedback action.
3. Watch for a new coding agent run.
4. Inspect the task logs for plan-scope or workspace errors.
5. Confirm the new run reached a terminal or review state.
6. Refresh the change-set query.

Changing only frontend state cannot produce a new diff; a backend coding pass
must complete and save a new change set.

## Clean local database

If local development data is disposable, follow the destructive reset steps in
[Database Guide](database-guide.md#resetting-the-local-database).

Resetting the database is not a normal fix for a state-machine bug. Preserve the
failed record and logs until the cause is understood.

## Report a useful bug

Include:

- what you expected;
- what happened;
- task ID and approximate time;
- route and HTTP status;
- stable backend error code;
- relevant redacted log lines;
- last timeline event;
- whether the backend or Docker restarted;
- the smallest reproduction sequence.

Never include private keys, OAuth secrets, access tokens, cookies, or complete
authorization headers.

