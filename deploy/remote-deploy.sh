#!/usr/bin/env bash
# Ship the committed code to an instance and start KHelp.
#
#   ENV_SSM_PARAM=/khelp/prod/env deploy/remote-deploy.sh ubuntu@<ip> ~/.ssh/<key>.pem
#
# Settings live in one SSM SecureString parameter (a JSON object of environment variables). The
# instance reads it with its own IAM role (deploy/env-sync.sh) and writes /opt/khelp/.env (mode 600);
# secrets never pass through the machine running this script. A systemd timer re-checks the
# parameter every minute, so changing a setting in SSM (e.g. KHELP_USE_LOCAL_MODEL) needs no redeploy.
#
# Copies `git archive HEAD` (committed files only). Re-running redeploys HEAD; data volumes are kept.
set -euo pipefail

HOST="${1:?usage: remote-deploy.sh user@host key.pem}"
KEY="${2:?usage: remote-deploy.sh user@host key.pem}"
: "${ENV_SSM_PARAM:?set ENV_SSM_PARAM, e.g. /khelp/prod/env}"
SSH=(ssh -i "$KEY" -o StrictHostKeyChecking=accept-new "$HOST")

cd "$(git rev-parse --show-toplevel)"
echo "Shipping $(git rev-parse --short HEAD) to $HOST (settings from $ENV_SSM_PARAM)"
git archive --format=tar HEAD | "${SSH[@]}" "sudo mkdir -p /opt/khelp && sudo chown \$USER /opt/khelp && tar -x -C /opt/khelp"

"${SSH[@]}" ENV_SSM_PARAM="$ENV_SSM_PARAM" bash -s <<'REMOTE'
set -euo pipefail
cd /opt/khelp

if ! command -v docker >/dev/null 2>&1; then
  curl -fsSL https://get.docker.com | sudo sh
fi
if ! sudo docker compose version >/dev/null 2>&1; then
  sudo apt-get update -qq && sudo apt-get install -y -qq docker-compose-plugin
fi
command -v aws >/dev/null 2>&1 || [ -x /snap/bin/aws ] || sudo snap install aws-cli --classic >/dev/null

# Small instances: swap so image builds never run out of memory.
if [ "$(awk '/MemTotal/ {print $2}' /proc/meminfo)" -lt 3500000 ] && ! swapon --show | grep -q swapfile; then
  sudo fallocate -l 2G /swapfile && sudo chmod 600 /swapfile && sudo mkswap /swapfile >/dev/null && sudo swapon /swapfile
  echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab >/dev/null
fi

echo "$ENV_SSM_PARAM" > .env-ssm-param
sudo deploy/env-sync.sh --build

sudo cp deploy/khelp-env-sync.service deploy/khelp-env-sync.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now khelp-env-sync.timer >/dev/null

for i in $(seq 1 90); do curl -sf localhost/api/health && break; sleep 2; done
echo
sudo docker compose ps --format 'table {{.Service}}\t{{.Status}}'
REMOTE

echo "Deployed to ${HOST}"
