#!/usr/bin/env bash

set -euo pipefail

REMOTE_HOST="${REMOTE_HOST:-win-local-via-reverse-ssh}"
REMOTE_DIR="${REMOTE_DIR:-D:/AI/Pivot_Client/seller_client}"
SCRIPT_REL_PATH="${1:?usage: run-windows-bootstrap.sh <relative-ps1-path> [args...]}"
shift || true

REMOTE_DIR_WIN="$(printf '%s' "$REMOTE_DIR" | tr '/' '\\')"
SCRIPT_REL_PATH_WIN="$(printf '%s' "$SCRIPT_REL_PATH" | tr '/' '\\')"
WIN_PATH="${REMOTE_DIR_WIN}\\${SCRIPT_REL_PATH_WIN}"
PS_ARGS=()

for arg in "$@"; do
  if [[ "$arg" == --* ]]; then
    PS_ARGS+=("-${arg#--}")
  elif [[ "$arg" == -* ]]; then
    PS_ARGS+=("${arg}")
  else
    escaped=${arg//\'/\'\'}
    PS_ARGS+=("'${escaped}'")
  fi
done

ARG_STRING=""
if ((${#PS_ARGS[@]} > 0)); then
  ARG_STRING=" ${PS_ARGS[*]}"
fi

ssh -o BatchMode=yes -o ConnectTimeout=5 "${REMOTE_HOST}" \
  "powershell -NoProfile -ExecutionPolicy Bypass -Command \"& '${WIN_PATH}'${ARG_STRING}\""
