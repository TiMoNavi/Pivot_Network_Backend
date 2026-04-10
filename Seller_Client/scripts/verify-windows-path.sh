#!/usr/bin/env bash

set -euo pipefail

REMOTE_HOST="${REMOTE_HOST:-win-local-via-reverse-ssh}"
WG_INTERFACE="${WG_INTERFACE:-wg0}"
WINDOWS_PEER_ALLOWED_IP="${WINDOWS_PEER_ALLOWED_IP:-10.66.66.10/32}"
SSH_OPTS=(
  -o BatchMode=yes
  -o ConnectTimeout=5
  -o ServerAliveInterval=5
  -o ServerAliveCountMax=1
)

echo "[1/3] WireGuard peer snapshot on ${WG_INTERFACE}"
if command -v wg >/dev/null 2>&1; then
  wg show "${WG_INTERFACE}" | sed -n "/${WINDOWS_PEER_ALLOWED_IP//\//\\/}/,+4p" || true
else
  echo "wg command not found locally; skipping peer snapshot"
fi

echo "[2/3] Windows SSH identity via ${REMOTE_HOST}"
ssh "${SSH_OPTS[@]}" "${REMOTE_HOST}" whoami

echo "[3/3] Remote overlay/runtime snapshot"
bash "$(cd -- "$(dirname "${BASH_SOURCE[0]}")" && pwd)/check-windows-overlay-runtime.sh"
