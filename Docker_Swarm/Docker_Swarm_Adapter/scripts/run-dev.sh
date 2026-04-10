#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd)"

cd "$PROJECT_DIR"
set -a
. "$PROJECT_DIR/.env"
set +a
. "$PROJECT_DIR/.venv/bin/activate"
exec python -m uvicorn app.main:app --host "${ADAPTER_HOST}" --port "${ADAPTER_PORT}"
