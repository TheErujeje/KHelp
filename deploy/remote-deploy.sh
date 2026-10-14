#!/usr/bin/env bash
# Ship the committed code to an instance and start KHelp.
#
#   ENV_SSM_PARAM=/khelp/prod/env deploy/remote-deploy.sh ubuntu@<ip> ~/.ssh/<key>.pem
#
# Settings come from one SSM SecureString parameter holding a JSON object of environment
# variables (see deploy/ec2-setup.md). The instance fetches it with its own IAM role and writes
# /opt/khelp/.env (mode 600); secrets never pass through the machine running this script.
#
# Which services start follows the settings:
#   KHELP_MODEL_PROVIDER=groq                                   app only
#   KHELP_MODEL_PROVIDER=ollama, OLLAMA_BASE_URL=http://ollama:11434   app + Ollama on this GPU box
#   KHELP_MODEL_PROVIDER=ollama, OLLAMA_BASE_URL=<other host>    app only, model on another box
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
if ! command -v aws >/dev/null 2>&1; then
  sudo snap install aws-cli --classic >/dev/null
fi

# Small instances: swap so image builds never run out of memory.
if [ "$(awk '/MemTotal/ {print $2}' /proc/meminfo)" -lt 3500000 ] && ! swapon --show | grep -q swapfile; then
  sudo fallocate -l 2G /swapfile && sudo chmod 600 /swapfile && sudo mkswap /swapfile >/dev/null && sudo swapon /swapfile
  echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab >/dev/null
fi

# Render .env from the SSM parameter (instance role; region from instance metadata).
REGION=$(TOKEN=$(curl -sX PUT http://169.254.169.254/latest/api/token -H "X-aws-ec2-metadata-token-ttl-seconds: 60") \
  && curl -s -H "X-aws-ec2-metadata-token: $TOKEN" http://169.254.169.254/latest/meta-data/placement/region)
umask 077
aws ssm get-parameter --region "$REGION" --name "$ENV_SSM_PARAM" --with-decryption \
  --query Parameter.Value --output text \
  | python3 -c '
import json, sys
env = json.load(sys.stdin)
for key, value in env.items():
    value = str(value)
    if "\n" in value or not key.replace("_", "").isalnum():
        sys.exit(f"invalid entry {key!r}")
    print(f"{key}={value}")
' > .env.new
mv .env.new .env
echo "wrote .env ($(wc -l < .env) settings)"

get() { grep -E "^$1=" .env | head -1 | cut -d= -f2-; }
PROVIDER=$(get KHELP_MODEL_PROVIDER)
if [ "$PROVIDER" = "ollama" ] && [ "$(get OLLAMA_BASE_URL)" = "http://ollama:11434" ]; then
  nvidia-smi --query-gpu=name,memory.total --format=csv,noheader
  COMPOSE=(sudo docker compose -f docker-compose.yml -f deploy/compose.gpu.yml --profile local-model)
  LOCAL_MODEL=1
else
  COMPOSE=(sudo docker compose)
  LOCAL_MODEL=0
fi
echo "model: $PROVIDER $(get KHELP_MODEL)"

"${COMPOSE[@]}" up -d --build --remove-orphans
if [ "$LOCAL_MODEL" = 1 ]; then
  echo "waiting for the model download (first deploy only)..."
  "${COMPOSE[@]}" logs -f ollama-pull 2>/dev/null | grep -m1 -E "success|Error" || true
fi
for i in $(seq 1 90); do curl -sf localhost/api/health && break; sleep 2; done
echo
"${COMPOSE[@]}" ps --format 'table {{.Service}}\t{{.Status}}'
REMOTE

echo "Open http://${HOST#*@}/"
