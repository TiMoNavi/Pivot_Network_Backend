#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=./cccc-control-common.sh
source "${SCRIPT_DIR}/cccc-control-common.sh"

normalize_terminal_env
ensure_control_dirs

cccc_cmd daemon start >/dev/null

group_id=$(resolve_group_id)
save_group_id "${group_id}"
ensure_group_active "${group_id}"
ensure_group_attached "${group_id}"
sync_group_metadata "${group_id}"
apply_group_template "${group_id}"
ensure_required_actors "${group_id}"
start_group_and_actors "${group_id}"

if ! is_web_listening; then
  launch_web_background
fi

if ! wait_for_actor_health "${group_id}"; then
  echo "actors unhealthy for group ${group_id}" >&2
  exit 1
fi

if ! wait_for_web; then
  echo "web unhealthy on port ${WEB_PORT}" >&2
  exit 1
fi

echo "healthy: group=${group_id} web=${WEB_HOST}:${WEB_PORT}"
