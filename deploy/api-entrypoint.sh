#!/bin/sh
# Migrate, seed synthetic patients (only into an empty database), then serve.
set -e
alembic -c packages/db/alembic.ini upgrade head
python -m khelp_api.seed
exec uvicorn khelp_api.main:app --host 0.0.0.0 --port 8000 \
  --workers "${KHELP_API_WORKERS:-1}" --proxy-headers --forwarded-allow-ips '*'
