#!/usr/bin/env bash
# Root-owned forced SSH command. Accepts only "deploy <40-character SHA>".
set -Eeuo pipefail
export PATH=/usr/local/bin:/usr/bin:/bin
umask 077
[[ $# == 1 && "$1" =~ ^deploy\ ([0-9a-f]{40})$ ]] || { echo 'Invalid deployment command' >&2; exit 2; }
revision="${BASH_REMATCH[1]}"
exec 9>/run/lock/repopilot-deploy.lock
flock -n 9 || { echo 'Another deployment is running' >&2; exit 1; }
base=/opt/repopilot
releases=/opt/repopilot-releases
backups=/opt/repopilot-backups
install -d -o repopilot -g repopilot -m 750 "$releases"
install -d -m 700 "$backups"
release=$(mktemp -d "$releases/${revision}.XXXXXX")
chown repopilot:repopilot "$release"
previous=$(readlink -f "$base/current")
maintenance=0
stopped=0
switched=0
success=0
finish() {
    result=$?
    trap - EXIT
    if (( success == 0 )); then
        echo 'Deployment failed; retaining/restoring previous application release.' >&2
        if (( switched )); then
            ln -sfn "$previous" "$base/current.next"
            mv -Tf "$base/current.next" "$base/current"
        fi
        if (( stopped )); then
            systemctl restart repopilot-api repopilot-frontend || true
        fi
        rm -rf -- "$release"
    fi
    if (( maintenance )); then
        cp /etc/caddy/Caddyfile.repopilot-normal /etc/caddy/Caddyfile
        systemctl reload caddy || result=1
    fi
    exit "$result"
}
trap finish EXIT
# Extraction is unprivileged; git archive is supplied by the trusted branch workflow.
sudo -u repopilot tar -xz --no-same-owner -C "$release"
[[ -f "$release/backend/requirements-runtime.txt" && -f "$release/frontend/package-lock.json" ]]
[[ ! -e "$release/.env" && ! -L "$release/.env" ]] || { echo 'Archive contains .env' >&2; exit 1; }
ln -s "$base/.env" "$release/.env"
printf '%s\n' "$revision" > "$release/REVISION"
chown -h repopilot:repopilot "$release/.env"
sudo -u repopilot python3 -m venv "$release/backend/.venv"
sudo -u repopilot "$release/backend/.venv/bin/pip" install --quiet -r "$release/backend/requirements-runtime.txt"
sudo -u repopilot "$release/backend/.venv/bin/pip" check
sudo -u repopilot env PYTHONPATH="$release/backend" "$release/backend/.venv/bin/python" -c 'import app.main'
sudo -u repopilot bash -c 'cd "$1/frontend"; export PATH=/usr/local/bin:/usr/bin:/bin NEXT_TELEMETRY_DISABLED=1 REPOPILOT_API_URL=http://127.0.0.1:8000; npm ci --no-audit --no-fund && npm test && npm run build' bash "$release"
# Reject active work, including transitions between operation locks.
assert_idle() {
    count=$(docker exec repopilot-postgres psql -U repopilot -d repopilot -Atc "SELECT (SELECT count(*) FROM task_operation_locks WHERE expires_at > now()) + (SELECT count(*) FROM repo_pilot_tasks WHERE status NOT IN ('completed','failed','cancelled','plan_rejected','review_rejected','plan_pending_approval','plan_revision_required','review_pending'));" )
    [[ "$count" == 0 ]] || { echo 'Active RepoPilot tasks: rerun deployment after they finish.' >&2; return 1; }
}
assert_idle
# Block new requests before checking again; existing in-flight requests can finish.
cat > /etc/caddy/repopilot-maintenance.Caddyfile <<'CADDY'
repopilot.35-255-102-56.sslip.io {
    respond "RepoPilot deployment in progress. Please retry shortly." 503
}
CADDY
caddy validate --config /etc/caddy/repopilot-maintenance.Caddyfile --adapter caddyfile
cp /etc/caddy/Caddyfile /etc/caddy/Caddyfile.repopilot-normal
maintenance=1
cp /etc/caddy/repopilot-maintenance.Caddyfile /etc/caddy/Caddyfile
systemctl reload caddy
sleep 3
assert_idle
stopped=1
systemctl stop repopilot-api repopilot-frontend
backup="$backups/$(date -u +%Y%m%dT%H%M%SZ)-${revision}.dump"
docker exec repopilot-postgres pg_dump -U repopilot -d repopilot -Fc > "$backup"
# Migrations must remain backward compatible with the previous app release.
sudo -u repopilot bash -c 'cd "$1/backend"; .venv/bin/python -m alembic upgrade head' bash "$release"
ln -sfn "$release" "$base/current.next"
mv -Tf "$base/current.next" "$base/current"
switched=1
systemctl start repopilot-api repopilot-frontend
healthy=0
for attempt in {1..30}; do
    if curl -fsS --max-time 3 http://127.0.0.1:8000/ready >/dev/null && curl -fsS --max-time 3 http://127.0.0.1:3000/login >/dev/null; then
        healthy=1
        break
    fi
    sleep 2
 done
[[ "$healthy" == 1 ]] || { echo 'Release health check failed' >&2; exit 1; }
success=1
# Keep three releases and seven DB backups; never remove the current or prior release.
python3 - "$release" "$previous" <<'PY'
from pathlib import Path
import shutil,sys
protected={Path(x).resolve() for x in sys.argv[1:]}
releases=sorted(Path('/opt/repopilot-releases').iterdir(),key=lambda p:p.stat().st_mtime,reverse=True)
for p in releases[3:]:
    if p.is_dir() and p.resolve() not in protected: shutil.rmtree(p)
backups=sorted(Path('/opt/repopilot-backups').glob('*.dump'),key=lambda p:p.stat().st_mtime,reverse=True)
for p in backups[7:]: p.unlink()
PY
printf 'Deployed %s successfully\n' "$revision"
