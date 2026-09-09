# Google Cloud deployment

Deployed September 9, 2026 from commit `161f7584af6956278dcf1046e96b95511b2e896d`.

- Website: https://repopilot.35-255-102-56.sslip.io
- Project: `project-07c32f0e-337e-4a1b-9d4`
- VM: `repopilot`, `us-central1-a`, Ubuntu 24.04, `e2-standard-2` (2 vCPUs, 8 GB RAM)
- Disk: 50 GB balanced persistent disk; daily snapshot schedule `default-schedule-1`
- Public IP: `35.255.102.56` (ephemeral; static promotion did not complete in the console)
- Source on VM: `/opt/repopilot` (uploaded from local Git archive; no remote Git credentials)
- Database: PostgreSQL 17 + pgvector, Docker container `repopilot-postgres`, named volume `repopilot_postgres`
- API and frontend: systemd services `repopilot-api` and `repopilot-frontend`
- HTTPS: Caddy, automatic certificate renewal

## Cost

Console estimated $53.92/month for compute and disk, before public IPv4, traffic,
snapshots and other variable usage. This uses the Google Cloud trial credit;
it is not an ongoing free-tier deployment. Trial showed ₹28,663.51 and expiry
December 9, 2026 at provisioning. The full paid account was not activated.
OpenAI API charges are separate.

## Access and configuration

```sh
ssh -i ~/.ssh/repopilot_gcp repopilot-deploy@35.255.102.56
sudo systemctl status repopilot-api repopilot-frontend caddy
sudo journalctl -u repopilot-api -n 100
sudo journalctl -u repopilot-frontend -n 100
```

Secrets are in `/opt/repopilot/.env` (mode 600, owned by `repopilot`) and
`/opt/repopilot/postgres.env` (mode 600, root-owned). Never commit either file.
Keep the session and GitHub token encryption secrets stable when updating.
The VM has no Google Cloud service account attached.

Backend port 8000, frontend port 3000 and PostgreSQL port 5432 bind to loopback.
Caddy exposes HTTP/HTTPS. SSH uses a dedicated instance key held on this Mac.

The runtime dependencies are installed using `backend/requirements-runtime.txt`,
with transitive versions constrained by `backend/requirements.txt`.
Node 22.23.2 is installed in `/usr/local/bin`; Python uses Ubuntu's Python 3.12
in `/opt/repopilot/backend/.venv`. Systemd runs as `repopilot` with Docker access.
Sandbox containers use UID/GID `997:988` and have CPU, RAM, PID and timeout limits.
Workspaces are `/opt/repopilot/backend/workspaces`; sandboxes are
`/opt/repopilot/sandboxes`.

GitHub App `harshrepopilot` uses the deployment hostname as its homepage and
installation callback. The production OAuth callback was added alongside the
existing localhost callback:

- `/api/v1/auth/github/callback`
- `/api/v1/auth/github/installations/callback`

## Validation performed

- Production frontend build and TypeScript compilation passed.
- Python runtime `pip check` passed; API import passed.
- All Alembic migrations applied to an empty database.
- Public HTTPS `/ready` returned 200 with all five checks healthy.
- Real Docker sandbox Python execution and cleanup passed.
- GitHub OAuth login completed; authenticated dashboard and repository list loaded.

No AI coding task or pull request was created as part of the deployment check.

## Updating

Transfer the intended code revision to the VM without overwriting `.env`,
`backend/.venv`, workspaces, sandboxes or database storage. Then, as `repopilot`:

```sh
cd /opt/repopilot/backend
.venv/bin/pip install -r requirements-runtime.txt
.venv/bin/python -m alembic upgrade head
cd /opt/repopilot/frontend
PATH=/usr/local/bin:/usr/bin:/bin npm ci
PATH=/usr/local/bin:/usr/bin:/bin REPOPILOT_API_URL=http://127.0.0.1:8000 npm run build
```

Restart the two RepoPilot services after the build and migrations succeed.
Schedule updates when no task is executing; task orchestration runs in-process.

The database is new and does not contain local development task history.
Keep database dumps outside the VM in addition to disk snapshots before any
schema change or deleting cloud resources.

## IP address limitation

The current address is ephemeral. Do not stop/start the VM expecting the hostname
to stay unchanged. Promote the existing address to static from VPC Network → IP
addresses when the console allows it. If the address changes, update Caddy, the
production environment URLs, and GitHub App callback URLs together.

## Automatic deployment

Pushes to **`develop`**, the repository's default branch, run
`.github/workflows/deploy.yml`. Other branches and pull requests do not deploy.
You can also select **Run workflow** under GitHub Actions → Deploy RepoPilot.

The runner sends the pushed commit as a Git archive over verified SSH. A dedicated
`repopilot-ci` account accepts only the forced `deploy <SHA>` command; its key has
no interactive shell, PTY, or forwarding access. GitHub stores the encrypted
`REPOPILOT_DEPLOY_KEY`, `REPOPILOT_KNOWN_HOSTS`, and `REPOPILOT_DEPLOY_HOST` secrets,
and the `REPOPILOT_SITE_URL` variable. App credentials remain on the VM.

The root-owned receiver is `/usr/local/sbin/repopilot-deploy`, installed from
`scripts/deploy/receive.sh`. Changes to that script require an administrator to
install it on the VM; deployed application code cannot automatically replace it.
The one-time setup is recorded in `scripts/deploy/bootstrap.sh` (expects the
receiver and public key staged in `/tmp` as indicated by that script).

Each deployment builds in `/opt/repopilot-releases/<SHA>.<suffix>`, runs frontend
tests and production compilation, checks Python dependencies and API imports,
then refuses to interrupt active tasks. During the short switchover it serves a
maintenance response, stops the app, backs up PostgreSQL, applies migrations,
switches `/opt/repopilot/current`, and starts both app services. Local and public
HTTP health checks verify the result. Builds run as `repopilot`, not root.

The live systemd services now use `/opt/repopilot/current/backend` and
`/opt/repopilot/current/frontend`. `WORKSPACE_ROOT` explicitly retains the stable
`/opt/repopilot/backend/workspaces` directory across releases; the database,
sandbox directory, and `.env` are also retained. Three recent release directories
and seven database dumps are retained (plus the protected previous release).
DB dumps are root-only under `/opt/repopilot-backups`; the original manual
installation remains available at `/opt/repopilot` as the initial fallback.

If startup or local health checks fail, the receiver restores the prior app
release. **Database migrations are not automatically reversed**; migrations must
be backward compatible. Destructive schema changes need a separate migration
plan. Failed builds leave the current application running. If active tasks block
a deployment, rerun the workflow after they finish. Concurrent deployments are
serialized; an in-progress deployment is not cancelled by a newer push.

If the ephemeral VM IP changes, update the deployment host and known-hosts
secrets as well as the hostname configuration described above. This workflow
uses GitHub-hosted Actions minutes, subject to the account's included allowance.
