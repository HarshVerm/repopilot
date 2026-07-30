# Free-Tier Deployment Guide

This guide deploys a small RepoPilot demo with approximately **$0 monthly
infrastructure cost**.

Free-tier offers change frequently. The limits in this guide were checked on
**July 30, 2026**. Confirm every provider's current pricing before creating
resources.

## Important: the complete application is not completely free

The hosting infrastructure can fit inside a free tier, but:

- OpenAI API usage is billed separately;
- a custom domain may cost money;
- usage above a cloud provider's free allowance may be charged or stopped;
- free resources have no production uptime guarantee;
- GitHub organization owners may need to approve the App installation.

Use this setup for development, demonstrations, and a small private beta. Move
to paid infrastructure before promising availability to external users.

## Recommended free architecture

The most compatible free option is one
[Oracle Cloud Always Free](https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm)
Ampere A1 VM.

```mermaid
flowchart TD
    U[User browser] --> C[Caddy HTTPS reverse proxy]
    C --> F[Next.js on port 3000]
    C --> B[FastAPI on port 8000]
    B --> P[(Local PostgreSQL and pgvector)]
    B --> W[Persistent task workspaces]
    B --> D[Docker verification sandbox]
    B --> G[GitHub API]
    B --> O[OpenAI API]
```

Run all of these on one VM:

- Caddy;
- Next.js;
- FastAPI;
- PostgreSQL with pgvector;
- persistent task workspaces;
- Docker verification containers.

This matches RepoPilot's current single-process background workflow and avoids
cross-host cookie, storage, and Docker problems.

## Why Oracle A1 is the first choice

Oracle's current Always Free documentation lists a total allowance equivalent
to:

- 2 Arm OCPUs;
- 12 GB memory;
- 200 GB combined boot and block-volume storage;
- five volume backups;
- 20 GB Object Storage.

That is enough for a low-traffic RepoPilot demo with one active task at a time.
Oracle warns that capacity can be unavailable in a home region and that idle
Always Free compute instances may be reclaimed. Keep backups and be prepared to
recreate the VM.

Most users also need a payment card to create an Oracle Cloud account, although
Oracle states that it is not charged unless the account is upgraded or paid
resources are used.

## Free-provider comparison

| Provider | Useful for RepoPilot? | Main limitation |
| --- | --- | --- |
| Oracle Cloud A1 Always Free | **Recommended for a demo** | Arm architecture, regional capacity, possible idle reclamation, no SLA |
| Neon Free Postgres | Optional managed database | 0.5 GB storage per project and 100 CU-hours; compute scales down when idle |
| Supabase Free Postgres | Optional managed database | 500 MB database per project; free-project restrictions |
| Google Cloud `e2-micro` | Not recommended for the full app | About 1 GB RAM and fractional shared CPU are below RepoPilot's practical needs |
| Render Free | Not suitable for the full app | Sleeps after 15 minutes, ephemeral filesystem, no free persistent disk; free Postgres expires |
| Koyeb Free | Not suitable for the full app | Mandatory scale-to-zero and no durable workspace/Docker-daemon design |
| Fly.io | Not a continuing free option for new users | Current offer is a short trial, then usage-based billing |
| Vercel Hobby | Frontend preview only | Does not provide the persistent backend worker and Docker sandbox |

The free database alternatives support pgvector:

- [Neon documents pgvector support](https://neon.com/docs/ai/ai-concepts).
- [Supabase lists the `vector` extension](https://supabase.com/docs/guides/database/extensions).

For the first deployment, local PostgreSQL on the Oracle VM is simpler and has
more useful storage than either free managed database.

## Before starting

You need:

- an Oracle Cloud account;
- a GitHub App;
- an OpenAI API key with billing enabled;
- a public Git repository or a deploy key that can clone this application;
- an HTTPS hostname pointing to the VM.

A paid domain is not included in the infrastructure free tier. A free dynamic
DNS hostname can work for a demo, but its stability and terms are controlled by
that DNS provider.

## Step 1: Create the Always Free VM

In the Oracle Cloud Console:

1. Select the home region carefully. Always Free compute must be created there.
2. Create a Compute instance.
3. Choose an Ubuntu image marked **Always Free Eligible**.
4. Choose `VM.Standard.A1.Flex`.
5. Allocate 2 OCPUs and 12 GB memory.
6. Allocate a 100 GB boot volume, staying within the documented 200 GB total
   Always Free block-volume allowance.
7. Add your SSH public key.
8. Assign a public IPv4 address.

If Oracle reports **Out of host capacity**, try another availability domain in
the home region or retry later. Do not accidentally select a paid shape.

## Step 2: Configure network access

Allow only:

| Port | Source | Purpose |
| --- | --- | --- |
| 22/TCP | Your IP address | SSH administration |
| 80/TCP | Internet | HTTPS redirect and certificate challenge |
| 443/TCP | Internet | RepoPilot HTTPS |

Do not expose ports 3000, 5432, 8000, or the Docker daemon.

Oracle security lists control subnet ingress. Docker also warns that published
container ports can bypass some host firewall rules, so use the cloud security
list as the outer boundary and bind PostgreSQL to `127.0.0.1`.

See:

- [Oracle security lists](https://docs.oracle.com/en-us/iaas/Content/Network/Concepts/securitylists.htm)
- [Docker's firewall warning](https://docs.docker.com/engine/install/ubuntu/#firewall-limitations)

## Step 3: Install server software

Install:

- Git;
- Python 3.11 and its virtual-environment module;
- Node.js 20 or newer;
- Docker Engine and the Docker Compose plugin;
- Caddy.

Use Docker's
[official Ubuntu installation instructions](https://docs.docker.com/engine/install/ubuntu/).
Docker supports Ubuntu on Arm64.

Confirm everything:

```bash
git --version
python3.11 --version
node --version
npm --version
docker --version
docker compose version
caddy version
```

Create a dedicated application account:

```bash
sudo useradd --create-home --shell /bin/bash repopilot
sudo usermod --append --groups docker repopilot
sudo mkdir -p /opt/repopilot
sudo chown repopilot:repopilot /opt/repopilot
```

Membership in the `docker` group is effectively root-level access. Do not give
the `repopilot` account to other users and do not run unrelated applications
under it.

## Step 4: Clone RepoPilot

Switch to the application account and clone your repository:

```bash
sudo -iu repopilot
git clone YOUR_REPOPILOT_GIT_URL /opt/repopilot
cd /opt/repopilot
```

Replace `YOUR_REPOPILOT_GIT_URL` with the real clone URL.

## Step 5: Configure production secrets

Create the environment file from the example:

```bash
cd /opt/repopilot
cp .env.example .env
chmod 600 .env
```

Generate two different secrets:

```bash
openssl rand -hex 32
openssl rand -hex 32
```

Use one output for `SESSION_SECRET` and the other for
`GITHUB_USER_TOKEN_ENCRYPTION_SECRET`.

Create a separate secret directory for the GitHub App key:

```bash
mkdir -p /opt/repopilot/secrets
chmod 700 /opt/repopilot/secrets
```

Copy the downloaded GitHub App private key to:

```text
/opt/repopilot/secrets/github-app.private-key.pem
```

Then restrict it:

```bash
chmod 600 /opt/repopilot/secrets/github-app.private-key.pem
```

Use this production shape in `.env`:

```dotenv
APP_ENV=production
TASK_LOG_LEVEL=INFO
APP_BASE_URL=https://repopilot.example.com
FRONTEND_URL=https://repopilot.example.com
SESSION_SECRET=GENERATED_SESSION_SECRET
COOKIE_SECURE=true
COOKIE_DOMAIN=
ALLOW_LEGACY_UNAUTHENTICATED_API=false

GITHUB_APP_ID=YOUR_APP_ID
GITHUB_APP_PRIVATE_KEY=
GITHUB_APP_PRIVATE_KEY_PATH=/opt/repopilot/secrets/github-app.private-key.pem
GITHUB_APP_CLIENT_ID=YOUR_CLIENT_ID
GITHUB_APP_CLIENT_SECRET=YOUR_CLIENT_SECRET
GITHUB_APP_SLUG=YOUR_APP_SLUG
GITHUB_USER_TOKEN_ENCRYPTION_SECRET=GENERATED_ENCRYPTION_SECRET

OPENAI_API_KEY=YOUR_OPENAI_API_KEY

POSTGRES_PASSWORD=GENERATED_DATABASE_PASSWORD
DATABASE_URL=postgresql+asyncpg://repopilot:GENERATED_DATABASE_PASSWORD@127.0.0.1:5432/repopilot
```

Replace every uppercase placeholder. Use a random hexadecimal database
password so it does not require URL escaping.

Never commit `.env`, the GitHub private key, or generated secrets.

## Step 6: Start PostgreSQL safely

The repository's development Compose file publishes PostgreSQL on every host
interface. For the server, create `docker-compose.production.yml` with a
loopback-only binding:

```yaml
services:
  postgres:
    image: pgvector/pgvector:pg17
    restart: unless-stopped
    environment:
      POSTGRES_DB: repopilot
      POSTGRES_USER: repopilot
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    ports:
      - "127.0.0.1:5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data

volumes:
  postgres_data:
```

Start it:

```bash
cd /opt/repopilot
docker compose --env-file .env -f docker-compose.production.yml up -d
docker compose -f docker-compose.production.yml ps
```

The named Docker volume is stored on the VM's persistent boot volume.

## Step 7: Install and migrate the backend

```bash
cd /opt/repopilot/backend
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
python -m alembic upgrade head
```

Test configuration and database readiness:

```bash
PYTHONPATH=. python -m pytest -q
```

## Step 8: Build the frontend

```bash
cd /opt/repopilot/frontend
npm ci
REPOPILOT_API_URL=http://127.0.0.1:8000 npm run build
```

The browser will use the public hostname. The Next.js server proxies `/api/v1`,
`/health`, and `/ready` to the private FastAPI port.

## Step 9: Preload sandbox images

The default verification images are multi-architecture:

```bash
docker pull node:20-bookworm-slim
docker pull python:3.11-slim
```

Arm compatibility still depends on each user's repository. A dependency that
ships only an x86 binary can fail on an A1 VM even when RepoPilot itself works.

## Step 10: Run both applications with systemd

Create `/etc/systemd/system/repopilot-backend.service`:

```ini
[Unit]
Description=RepoPilot FastAPI backend and workflow
After=network-online.target docker.service
Wants=network-online.target
Requires=docker.service

[Service]
Type=simple
User=repopilot
Group=repopilot
SupplementaryGroups=docker
WorkingDirectory=/opt/repopilot/backend
ExecStart=/opt/repopilot/backend/.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
Restart=on-failure
RestartSec=5
TimeoutStopSec=900

[Install]
WantedBy=multi-user.target
```

Create `/etc/systemd/system/repopilot-frontend.service`:

```ini
[Unit]
Description=RepoPilot Next.js frontend
After=network-online.target repopilot-backend.service
Wants=network-online.target

[Service]
Type=simple
User=repopilot
Group=repopilot
WorkingDirectory=/opt/repopilot/frontend
Environment=NODE_ENV=production
Environment=REPOPILOT_API_URL=http://127.0.0.1:8000
ExecStart=/usr/bin/npm run start -- --hostname 127.0.0.1 --port 3000
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

If `command -v npm` is not `/usr/bin/npm`, use the returned absolute path in
`ExecStart`.

Enable and start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now repopilot-backend
sudo systemctl enable --now repopilot-frontend
sudo systemctl status repopilot-backend
sudo systemctl status repopilot-frontend
```

The current task runner lives inside the backend process. Restarting the backend
can interrupt active tasks, even though systemd starts the process again.

## Step 11: Configure HTTPS with Caddy

Point your hostname's DNS `A` record to the VM public IP. Then configure Caddy:

```caddyfile
repopilot.example.com {
    @backend path /api/* /health /ready

    handle @backend {
        reverse_proxy 127.0.0.1:8000
    }

    handle {
        reverse_proxy 127.0.0.1:3000
    }
}
```

Replace `repopilot.example.com`, validate the configuration, and reload Caddy:

```bash
sudo caddy validate --config /etc/caddy/Caddyfile
sudo systemctl reload caddy
```

Caddy provides
[automatic HTTPS](https://caddyserver.com/docs/automatic-https) when a valid
public hostname points to the server and ports 80 and 443 are reachable.

## Step 12: Update the GitHub App

In the GitHub App settings, replace localhost with the public hostname:

```text
Homepage URL:
https://repopilot.example.com

Callback URL:
https://repopilot.example.com/api/v1/auth/github/callback

Setup URL:
https://repopilot.example.com/api/v1/auth/github/installations/callback
```

Required repository permissions:

| Permission | Access |
| --- | --- |
| Metadata | Read-only |
| Contents | Read and write |
| Issues | Read and write |
| Pull requests | Read and write |

For a public multi-user application, choose **Any account** only after testing
the security and failure paths.

## Step 13: Verify the deployment

```bash
curl https://repopilot.example.com/health
curl https://repopilot.example.com/ready
```

Then perform a complete smoke test:

1. Sign in with GitHub.
2. Install the GitHub App for one test repository.
3. Confirm the repository and issue appear.
4. Create a small task.
5. Confirm indexing, planning, coding, and verification complete.
6. Review the exact diff.
7. Request changes once and confirm a new review is generated.
8. Approve the new diff.
9. Publish a pull request.
10. Confirm GitHub shows the signed-in user as the PR creator.

## Updating the deployed code

Do not restart the backend while a task is active.

When tasks are idle:

```bash
sudo -iu repopilot
cd /opt/repopilot
git pull --ff-only

cd backend
source .venv/bin/activate
pip install -r requirements.txt
python -m alembic upgrade head

cd ../frontend
npm ci
REPOPILOT_API_URL=http://127.0.0.1:8000 npm run build

sudo systemctl restart repopilot-backend
sudo systemctl restart repopilot-frontend
```

Run automated checks before restarting public services when possible.

## Backups

Free infrastructure is recoverable only if you keep backups outside the VM.

Back up:

- PostgreSQL with `pg_dump`;
- the `.env` file in an encrypted password manager;
- the GitHub App private key in secure encrypted storage;
- any active workspace needed for incident recovery.

Oracle currently documents five Always Free volume backups and 20 GB of Object
Storage. Do not keep the only database backup on the same boot volume as the
database.

Test restoring a backup before inviting users.

## Optional: use Neon instead of local PostgreSQL

Neon's current Free plan lists:

- 0.5 GB storage per project;
- 100 CU-hours per month per project;
- automatic scale-to-zero when inactive;
- pgvector support.

This can work for a small demo, but repository chunks and 1536-dimension
embeddings can use 0.5 GB quickly.

Create the Neon database, enable the `vector` extension, then use the provider's
TLS-enabled connection string. RepoPilot uses SQLAlchemy's asyncpg dialect, so
the URL starts with:

```text
postgresql+asyncpg://
```

Preserve Neon's required TLS parameters. Run:

```bash
cd /opt/repopilot/backend
source .venv/bin/activate
python -m alembic upgrade head
```

See:

- [Neon Free pricing](https://neon.com/pricing)
- [Neon Python and asyncpg connection guide](https://neon.com/docs/guides/python)
- [Neon pgvector support](https://neon.com/docs/ai/ai-concepts)

## Why the common free web hosts are not enough

### Render

Render documents that a free web service:

- spins down after 15 idle minutes;
- loses local filesystem changes after restart or spin-down;
- cannot attach a free persistent disk;
- may restart at any time.

Its free PostgreSQL database currently expires after 30 days. That is unsuitable
for active RepoPilot workspaces and process-local background tasks.

### Koyeb

Koyeb documents that its Free Instance automatically scales to zero after one
hour without traffic and that this cannot be disabled. A task page polling the
API is not a reliable substitute for a durable worker.

### Fly.io

Fly.io's current documentation describes a limited trial for new users rather
than a continuing general free allowance.

### Google Cloud `e2-micro`

Google's free VM is persistent and supports general Linux software, but its
documented `e2-micro` shape has about 1 GB RAM and only a fraction of shared CPU
capacity. RepoPilot's default Docker sandbox alone permits 2 GB RAM, so this VM
is too small for the complete application.

## Free-tier operating limits

For a stable demo:

- allow one active task at a time;
- keep `EVALUATION_MAX_CONCURRENCY=1`;
- do not run evaluation suites beside user tasks;
- clean completed workspaces after an intentional retention period;
- monitor Docker image and volume disk usage;
- monitor OpenAI token cost;
- back up the database;
- expect cold starts if using a free managed database;
- expect the VM to be replaceable, not permanent.

## When to upgrade

Move to paid infrastructure when:

- external users depend on the application;
- several tasks run concurrently;
- the RAG database approaches its storage limit;
- an Arm-only incompatibility affects repositories;
- backend restarts must not interrupt jobs;
- you need security support, an SLA, or automated recovery.

The first architectural upgrade should be a durable queue and separate worker,
followed by an isolated sandbox worker host.

## Official free-tier references

- [Oracle Always Free resources](https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm)
- [Oracle Cloud Free Tier FAQ](https://www.oracle.com/apac/cloud/free/faq/)
- [Neon pricing](https://neon.com/pricing)
- [Supabase free-plan billing](https://supabase.com/docs/guides/platform/billing-on-supabase)
- [Render free-instance limitations](https://render.com/docs/free)
- [Koyeb scale-to-zero](https://www.koyeb.com/docs/run-and-scale/scale-to-zero)
- [Fly.io pricing and legacy allowances](https://fly.io/docs/about/pricing/)
- [Google Cloud Free Program](https://docs.cloud.google.com/free/docs/free-cloud-features)
