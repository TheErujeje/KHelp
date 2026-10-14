#!/usr/bin/env bash
# Ship the committed code to a GPU instance and start KHelp with the self-hosted model.
#
#   deploy/remote-deploy.sh ubuntu@<ip> ~/.ssh/<key>.pem
#
# Copies `git archive HEAD` (committed files only, never .env), creates /opt/khelp/.env with
# random database passwords on first deploy, and runs compose with the GPU override.
# Re-running redeploys the current HEAD and keeps the existing .env and data.
set -euo pipefail

HOST="${1:?usage: remote-deploy.sh user@host key.pem}"
KEY="${2:?usage: remote-deploy.sh user@host key.pem}"
MODEL="${KHELP_MODEL:-qwen2.5:14b-instruct}"
SSH=(ssh -i "$KEY" -o StrictHostKeyChecking=accept-new "$HOST")

cd "$(git rev-parse --show-toplevel)"
echo "Shipping $(git rev-parse --short HEAD) to $HOST"
git archive --format=tar HEAD | "${SSH[@]}" "sudo mkdir -p /opt/khelp && sudo chown \$USER /opt/khelp && tar -x -C /opt/khelp"

"${SSH[@]}" MODEL="$MODEL" bash -s <<'REMOTE'
set -euo pipefail
cd /opt/khelp

# Docker compose plugin and NVIDIA runtime (the DLAMI ships Docker and the toolkit).
if ! docker compose version >/dev/null 2>&1; then
  sudo apt-get update -qq && sudo apt-get install -y -qq docker-compose-plugin \
    || { curl -fsSL https://get.docker.com | sudo sh; }
fi
sudo usermod -aG docker "$USER" || true
nvidia-smi --query-gpu=name,memory.total --format=csv,noheader

if [ ! -f .env ]; then
  cp .env.example .env
  sed -i "s/^POSTGRES_PASSWORD=.*/POSTGRES_PASSWORD=$(openssl rand -hex 16)/" .env
  sed -i "s/^MCP_DB_PASSWORD=.*/MCP_DB_PASSWORD=$(openssl rand -hex 16)/" .env
  sed -i "s/^KHELP_MODEL_PROVIDER=.*/KHELP_MODEL_PROVIDER=ollama/" .env
  sed -i "s/^KHELP_MODEL=.*/KHELP_MODEL=${MODEL}/" .env
  sed -i "s|^OLLAMA_BASE_URL=.*|OLLAMA_BASE_URL=http://ollama:11434|" .env
  chmod 600 .env
  echo "created .env (model ${MODEL})"
fi

sudo docker compose -f docker-compose.yml -f deploy/compose.gpu.yml --profile local-model up -d --build
echo "waiting for the model download (first deploy only)..."
sudo docker compose -f docker-compose.yml -f deploy/compose.gpu.yml --profile local-model logs -f ollama-pull 2>/dev/null \
  | grep -m1 -E "success|Error" || true
for i in $(seq 1 60); do curl -sf localhost/api/health && break; sleep 2; done
echo
sudo docker compose ps --format 'table {{.Service}}\t{{.Status}}'
REMOTE

echo "Open http://${HOST#*@}/"
