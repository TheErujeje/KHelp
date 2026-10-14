#!/usr/bin/env bash
# Ship the committed code to an instance and start KHelp.
#
#   deploy/remote-deploy.sh ubuntu@<ip> ~/.ssh/<key>.pem                      # self-hosted model on the GPU
#   PROVIDER=groq GROQ_API_KEY=... deploy/remote-deploy.sh ubuntu@<ip> key.pem # Groq (synthetic data only)
#
# Copies `git archive HEAD` (committed files only, never .env). On first deploy it creates
# /opt/khelp/.env with random database passwords. Re-running redeploys HEAD and keeps .env and data;
# PROVIDER/KHELP_MODEL/GROQ_API_KEY given on a re-run update the model settings.
set -euo pipefail

HOST="${1:?usage: remote-deploy.sh user@host key.pem}"
KEY="${2:?usage: remote-deploy.sh user@host key.pem}"
PROVIDER="${PROVIDER:-ollama}"
if [ "$PROVIDER" = "groq" ]; then
  MODEL="${KHELP_MODEL:-openai/gpt-oss-120b}"
  : "${GROQ_API_KEY:?PROVIDER=groq needs GROQ_API_KEY}"
else
  MODEL="${KHELP_MODEL:-qwen2.5:14b-instruct}"
fi
SSH=(ssh -i "$KEY" -o StrictHostKeyChecking=accept-new "$HOST")

cd "$(git rev-parse --show-toplevel)"
echo "Shipping $(git rev-parse --short HEAD) to $HOST (provider $PROVIDER, model $MODEL)"
git archive --format=tar HEAD | "${SSH[@]}" "sudo mkdir -p /opt/khelp && sudo chown \$USER /opt/khelp && tar -x -C /opt/khelp"

# The API key travels over SSH stdin into a 600 file; it never appears in a command line.
if [ "$PROVIDER" = "groq" ]; then
  printf '%s' "$GROQ_API_KEY" | "${SSH[@]}" "umask 077 && cat > /opt/khelp/.groq_key"
fi

"${SSH[@]}" PROVIDER="$PROVIDER" MODEL="$MODEL" bash -s <<'REMOTE'
set -euo pipefail
cd /opt/khelp

if ! command -v docker >/dev/null 2>&1; then
  curl -fsSL https://get.docker.com | sudo sh
fi
if ! sudo docker compose version >/dev/null 2>&1; then
  sudo apt-get update -qq && sudo apt-get install -y -qq docker-compose-plugin
fi

# Small instances: swap so image builds never run out of memory.
if [ "$(awk '/MemTotal/ {print $2}' /proc/meminfo)" -lt 3500000 ] && ! swapon --show | grep -q swapfile; then
  sudo fallocate -l 2G /swapfile && sudo chmod 600 /swapfile && sudo mkswap /swapfile >/dev/null && sudo swapon /swapfile
  echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab >/dev/null
fi

if [ ! -f .env ]; then
  cp .env.example .env
  sed -i "s/^POSTGRES_PASSWORD=.*/POSTGRES_PASSWORD=$(openssl rand -hex 16)/" .env
  sed -i "s/^MCP_DB_PASSWORD=.*/MCP_DB_PASSWORD=$(openssl rand -hex 16)/" .env
  chmod 600 .env
  echo "created .env"
fi

setvar() {  # setvar KEY VALUE: replace or append in .env
  if grep -qE "^#? ?$1=" .env; then sed -i "s|^#\? \?$1=.*|$1=$2|" .env; else echo "$1=$2" >> .env; fi
}
setvar KHELP_MODEL_PROVIDER "$PROVIDER"
setvar KHELP_MODEL "$MODEL"
if [ "$PROVIDER" = "groq" ]; then
  setvar GROQ_API_KEY "$(cat .groq_key)"
  setvar KHELP_REASONING_EFFORT low
  rm -f .groq_key
  COMPOSE=(sudo docker compose)
else
  setvar OLLAMA_BASE_URL http://ollama:11434
  nvidia-smi --query-gpu=name,memory.total --format=csv,noheader
  COMPOSE=(sudo docker compose -f docker-compose.yml -f deploy/compose.gpu.yml --profile local-model)
fi

"${COMPOSE[@]}" up -d --build
if [ "$PROVIDER" != "groq" ]; then
  echo "waiting for the model download (first deploy only)..."
  "${COMPOSE[@]}" logs -f ollama-pull 2>/dev/null | grep -m1 -E "success|Error" || true
fi
for i in $(seq 1 90); do curl -sf localhost/api/health && break; sleep 2; done
echo
"${COMPOSE[@]}" ps --format 'table {{.Service}}\t{{.Status}}'
REMOTE

echo "Open http://${HOST#*@}/"
