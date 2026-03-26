#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
. "$SCRIPT_DIR/common.sh"

load_env
require_swarm_active

docker run --rm \
  --network "${STACK_NAME}_internal" \
  --env-file "$ENV_FILE" \
  "$BACKEND_SWARM_IMAGE" \
  bash -lc 'cd /app/backend && export PYTHONPATH=/app/backend && /app/.venv/bin/python -m app.backend_pre_start && /app/.venv/bin/alembic upgrade head && /app/.venv/bin/python -m app.initial_data'
