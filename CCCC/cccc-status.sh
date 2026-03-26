#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=./cccc-control-common.sh
source "${SCRIPT_DIR}/cccc-control-common.sh"

normalize_terminal_env
ensure_control_dirs

if ! group_id=$(discover_existing_group_id 2>/dev/null); then
  echo "group is not initialized" >&2
  exit 1
fi

save_group_id "${group_id}"
ensure_group_active "${group_id}"

if ! actors_healthy "${group_id}"; then
  echo "actors unhealthy for group ${group_id}" >&2
  exit 1
fi

if ! is_web_listening; then
  echo "web unhealthy on port ${WEB_PORT}" >&2
  exit 1
fi

echo "healthy: group=${group_id} web=${WEB_HOST}:${WEB_PORT}"
