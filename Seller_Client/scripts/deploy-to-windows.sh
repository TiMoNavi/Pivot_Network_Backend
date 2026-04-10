#!/usr/bin/env bash

set -euo pipefail

REMOTE_HOST="${REMOTE_HOST:-win-local-via-reverse-ssh}"
REMOTE_DIR="${REMOTE_DIR:-D:/AI/Pivot_Client/seller_client}"
REMOTE_SHARED_DIR="${REMOTE_SHARED_DIR:-D:/AI/Pivot_Client}"
SCRIPT_DIR="$(cd -- "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd)"
REPO_ROOT="$(cd -- "$PROJECT_DIR/.." && pwd)"
CODEX_TEMPLATE_PATH="${REPO_ROOT}/env_setup_and_install/codex.config.toml"

echo "Deploying Seller_Client to ${REMOTE_HOST}:${REMOTE_DIR}"
ssh "${REMOTE_HOST}" "powershell -NoProfile -Command \"New-Item -ItemType Directory -Force '${REMOTE_DIR}' | Out-Null; New-Item -ItemType Directory -Force '${REMOTE_SHARED_DIR}/env_setup_and_install' | Out-Null\""
scp -r "${PROJECT_DIR}/"* "${REMOTE_HOST}:${REMOTE_DIR}/"
scp "${CODEX_TEMPLATE_PATH}" "${REMOTE_HOST}:${REMOTE_SHARED_DIR}/env_setup_and_install/codex.config.toml"
echo "Deployment complete."
