#!/usr/bin/env bash

set -euo pipefail

WINDOWS_WG_IP="${WINDOWS_WG_IP:-10.66.66.10}"
SERVER_WG_IFACE="${SERVER_WG_IFACE:-wg0}"

echo "== Pivot Seller Connectivity Doctor =="
echo
echo "[1/3] Checking TCP 22 on ${WINDOWS_WG_IP}"
if timeout 5 bash -lc "cat < /dev/null > /dev/tcp/${WINDOWS_WG_IP}/22"; then
  echo "tcp22-open"
else
  echo "tcp22-closed"
fi

echo
echo "[2/3] Checking WireGuard status on ${SERVER_WG_IFACE}"
if command -v wg >/dev/null 2>&1; then
  wg show "${SERVER_WG_IFACE}" || true
else
  echo "wg command not available"
fi

echo
echo "[3/3] SSH quick probe"
ssh -o BatchMode=yes -o ConnectTimeout=5 -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null "550w@${WINDOWS_WG_IP}" whoami || true
