#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=./cccc-control-common.sh
source "${SCRIPT_DIR}/cccc-control-common.sh"

normalize_terminal_env
ensure_control_dirs

stop_managed_web

if group_id=$(discover_existing_group_id 2>/dev/null); then
  cccc_cmd group stop --group "${group_id}" >/dev/null || true
fi

cccc_cmd daemon stop >/dev/null || true

echo "stopped"
