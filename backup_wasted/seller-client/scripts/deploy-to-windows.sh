#!/usr/bin/env bash

set -euo pipefail

REMOTE_HOST="${REMOTE_HOST:-win-local-via-wg}"
REMOTE_DIR="${REMOTE_DIR:-D:/AI/Pivot_Client}"
SCRIPT_DIR="$(cd -- "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd)"

echo "Deploying seller-client to ${REMOTE_HOST}:${REMOTE_DIR}"
ssh "${REMOTE_HOST}" "powershell -NoProfile -Command \"New-Item -ItemType Directory -Force '${REMOTE_DIR}' | Out-Null\""
scp -r "${PROJECT_DIR}/"* "${REMOTE_HOST}:${REMOTE_DIR}/"
echo "Deployment complete."
