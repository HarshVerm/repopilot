#!/bin/bash
set -euo pipefail
id repopilot-ci >/dev/null 2>&1 || useradd --create-home --shell /bin/bash repopilot-ci
install -d -o repopilot-ci -g repopilot-ci -m 700 /home/repopilot-ci/.ssh
install -o root -g root -m 755 /tmp/repopilot-receive.sh /usr/local/sbin/repopilot-deploy
cat > /usr/local/bin/repopilot-ci-command <<'COMMAND'
#!/bin/bash
exec sudo /usr/local/sbin/repopilot-deploy "${SSH_ORIGINAL_COMMAND:-}"
COMMAND
chmod 755 /usr/local/bin/repopilot-ci-command
printf '%s\n' 'repopilot-ci ALL=(root) NOPASSWD: /usr/local/sbin/repopilot-deploy *' > /etc/sudoers.d/repopilot-ci
chmod 440 /etc/sudoers.d/repopilot-ci
visudo -cf /etc/sudoers.d/repopilot-ci
{ printf 'restrict,command="/usr/local/bin/repopilot-ci-command" '; cat /tmp/repopilot-actions.pub; } > /home/repopilot-ci/.ssh/authorized_keys
chown repopilot-ci:repopilot-ci /home/repopilot-ci/.ssh/authorized_keys
chmod 600 /home/repopilot-ci/.ssh/authorized_keys
if [ ! -L /opt/repopilot/current ]; then ln -s /opt/repopilot /opt/repopilot/current; fi
if ! grep -q '^WORKSPACE_ROOT=' /opt/repopilot/.env; then printf '\nWORKSPACE_ROOT="/opt/repopilot/backend/workspaces"\n' >> /opt/repopilot/.env; fi
sed -i 's|/opt/repopilot/backend|/opt/repopilot/current/backend|g' /etc/systemd/system/repopilot-api.service
sed -i 's|/opt/repopilot/frontend|/opt/repopilot/current/frontend|g' /etc/systemd/system/repopilot-frontend.service
systemctl daemon-reload
printf 'CI deployment receiver installed\n'
