#!/usr/bin/env bash
# Render /opt/khelp/.env from the SSM parameter and (re)start the right services.
#
#   deploy/env-sync.sh            # timer mode: only acts when the parameter changed
#   deploy/env-sync.sh --build    # deploy mode: always rebuild and start
#
# Runs on the instance (IAM role reads the parameter). The parameter name is in
# /opt/khelp/.env-ssm-param. Which services start follows the settings:
#   KHELP_USE_LOCAL_MODEL=true and OLLAMA_BASE_URL=http://ollama:11434  -> app + Ollama on this GPU box
#   anything else                                                        -> app only
set -euo pipefail
cd /opt/khelp
export PATH="$PATH:/snap/bin"

PARAM=$(cat .env-ssm-param)
TOKEN=$(curl -sX PUT http://169.254.169.254/latest/api/token -H "X-aws-ec2-metadata-token-ttl-seconds: 60")
REGION=$(curl -s -H "X-aws-ec2-metadata-token: $TOKEN" http://169.254.169.254/latest/meta-data/placement/region)

umask 077
aws ssm get-parameter --region "$REGION" --name "$PARAM" --with-decryption --query Parameter.Value --output text \
  | python3 -c '
import json, sys
env = json.load(sys.stdin)
for key, value in env.items():
    if isinstance(value, dict):      # e.g. GROQ_API_KEYS as {"name": "key", ...}
        value = ",".join(str(v) for v in value.values())
    elif isinstance(value, list):
        value = ",".join(str(v) for v in value)
    value = str(value)
    if "\n" in value or not key.replace("_", "").isalnum():
        sys.exit(f"invalid entry {key!r}")
    print(f"{key}={value}")
' > .env.new

if [ "${1:-}" != "--build" ] && [ -f .env ] && cmp -s .env.new .env; then
  rm -f .env.new
  exit 0
fi
mv .env.new .env

get() { grep -E "^$1=" .env | head -1 | cut -d= -f2- || true; }
LOCAL=$(get KHELP_USE_LOCAL_MODEL | tr '[:upper:]' '[:lower:]')
if [ "$LOCAL" = "true" ] && [ "$(get OLLAMA_BASE_URL)" = "http://ollama:11434" ]; then
  COMPOSE=(docker compose -f docker-compose.yml -f deploy/compose.gpu.yml --profile local-model)
  MODEL="ollama (this box): $(get OLLAMA_MODEL)"
elif [ "$LOCAL" = "true" ]; then
  COMPOSE=(docker compose)
  MODEL="ollama at $(get OLLAMA_BASE_URL): $(get OLLAMA_MODEL)"
else
  COMPOSE=(docker compose)
  MODEL="hosted $(get KHELP_HOSTED_PROVIDER)"
fi
echo "$(date -Is) settings from $PARAM applied; model: $MODEL"

if [ "${1:-}" = "--build" ]; then
  "${COMPOSE[@]}" up -d --build --remove-orphans
else
  "${COMPOSE[@]}" up -d --remove-orphans   # recreates only containers whose settings changed
fi
