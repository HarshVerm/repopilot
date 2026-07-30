# RepoPilot GitHub App Setup

RepoPilot uses GitHub OAuth for user identity and GitHub App installations for
repository access. It does not ask users for personal access tokens and does
not persist installation access tokens. GitHub App user access and refresh
tokens are encrypted at rest so pull requests can be attributed to the
signed-in user.

Create a **GitHub App**, not a standalone OAuth App. GitHub Apps use the OAuth
web application flow for user sign-in while also providing fine-grained,
installation-scoped repository access:

- [Registering a GitHub App](https://docs.github.com/en/apps/creating-github-apps/registering-a-github-app/registering-a-github-app)
- [Generating a user access token for a GitHub App](https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/generating-a-user-access-token-for-a-github-app)

## 1. Create the GitHub App

In GitHub, open **Settings → Developer settings → GitHub Apps → New GitHub
App** and configure:

- **GitHub App name:** a unique name, such as `RepoPilot Development`
- **Homepage URL:** the frontend URL, such as `http://localhost:3000`
- **User authorization callback URL:**
  `http://localhost:8000/api/v1/auth/github/callback`
- **Setup URL (optional):**
  `http://localhost:8000/api/v1/auth/github/installations/callback`
- **Redirect on update:** enabled
- **Request user authorization (OAuth) during installation:** disabled;
  RepoPilot starts the user authorization flow explicitly
- **Webhook:** inactive unless a separate webhook handler is added
- **Where can this GitHub App be installed?:** Any account

For a deployed environment, replace `localhost:8000` with `APP_BASE_URL` and
use HTTPS.

## 2. Repository permissions

Grant only these repository permissions:

- **Metadata:** Read-only (GitHub grants this by default)
- **Contents:** Read and write
- **Issues:** Read and write
- **Pull requests:** Read and write

No organization administration or repository administration permission is
required. Installations can be limited to selected repositories or granted to
all repositories. RepoPilot only displays repositories returned for the
current installation.

Private repositories work through the same installation-token flow. An
organization installation may remain unavailable until an organization owner
approves it.

If the app was already installed with Issues read-only access, changing this
setting is not enough by itself. Open the installation on GitHub and approve
the requested permission update. Then refresh the repository list in
RepoPilot.

## 3. Generate credentials

After creating the app:

1. Copy the App ID, client ID, client secret, and app slug.
2. Generate a private key and download the PEM file.
3. Put the values in a local `.env`; never commit the PEM or secret.

```env
APP_ENV=development
APP_BASE_URL=http://localhost:8000
FRONTEND_URL=http://localhost:3000
SESSION_SECRET=replace-with-at-least-32-random-characters
COOKIE_SECURE=false
COOKIE_DOMAIN=
ALLOW_LEGACY_UNAUTHENTICATED_API=true

GITHUB_APP_ID=123456
GITHUB_APP_PRIVATE_KEY="-----BEGIN RSA PRIVATE KEY-----\n...\n-----END RSA PRIVATE KEY-----"
# Alternatively, use an absolute path instead of GITHUB_APP_PRIVATE_KEY:
# GITHUB_APP_PRIVATE_KEY_PATH=/absolute/path/to/github-app.private-key.pem
GITHUB_APP_CLIENT_ID=Iv1.example
GITHUB_APP_CLIENT_SECRET=example
GITHUB_APP_SLUG=repopilot-development
GITHUB_USER_TOKEN_ENCRYPTION_SECRET=replace-with-an-independent-32-character-secret

DATABASE_URL=postgresql+asyncpg://repopilot:repopilot@localhost:5432/repopilot
OPENAI_API_KEY=
```

Use independent random values for `SESSION_SECRET` and
`GITHUB_USER_TOKEN_ENCRYPTION_SECRET`. Production configuration forces secure
cookies, disables the unauthenticated compatibility API, and rejects missing
or weak secrets. Keep the token-encryption secret stable across deployments;
changing it requires users to reconnect GitHub.

The frontend uses:

```env
NEXT_PUBLIC_REPOPILOT_API_URL=http://localhost:8000
REPOPILOT_API_URL=http://localhost:8000
NEXT_PUBLIC_REPOPILOT_CSRF_COOKIE_NAME=repopilot_csrf
```

No GitHub or OpenAI secret belongs in a `NEXT_PUBLIC_*` variable.

When the public frontend and API use sibling production hosts, such as
`app.example.com` and `api.example.com`, set `COOKIE_DOMAIN=.example.com`.
Production startup rejects a cross-host configuration without it. If both are
served from one host through a reverse proxy, leave `COOKIE_DOMAIN` empty.

## 4. Prepare the application

With PostgreSQL and pgvector available:

```bash
cd backend
python3.11 -m pip install -r requirements.txt
python3.11 -m alembic upgrade head
python3.11 -m uvicorn app.main:app --reload
```

In a second terminal:

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:3000`, sign in with GitHub, then choose **Configure
GitHub Access**. After GitHub returns to RepoPilot, RepoPilot performs a second
user-bound OAuth verification. The installation is activated only if GitHub
confirms that the signed-in user can access that installation.

## 5. Token and publication behavior

RepoPilot encrypts the GitHub App user access token and optional rotating
refresh token before storing them. Expiring user tokens are refreshed
server-side using GitHub's rotation flow. The plaintext values are never
returned to the browser or written to logs. Existing users must open
**Settings → Pull request attribution → Connect User** once after upgrading.

An app JWT and a fresh, short-lived installation token are generated
server-side for repository listing, issue retrieval, cloning, and branch
pushes. Installation tokens are not persisted. Tokens passed to Git use a
temporary owner-only `GIT_ASKPASS` script and are redacted from errors.

After the exact final diff is approved, deterministic backend publication code
revalidates the installation, repository permission, diff hash, and base
commit. It then creates a non-default RepoPilot branch, commits and pushes the
approved files with the installation token, and opens the pull request with
the initiating user's access token. GitHub therefore displays the user's login
as the pull-request author instead of the App bot. RepoPilot never force-pushes,
pushes the default branch, or merges the pull request.

If an installation is removed, suspended, or loses repository access, a later
login, repository sync, or publication check marks the stored access state and
returns an actionable API error.
