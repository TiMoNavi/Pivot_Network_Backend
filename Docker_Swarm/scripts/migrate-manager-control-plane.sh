#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
. "$SCRIPT_DIR/_common.sh"

load_env
ensure_swarm_active

control_addr="${1:-$SWARM_CONTROL_ADDR}"
data_path_addr="${2:-$SWARM_DATA_PATH_ADDR}"
listen_addr="${SWARM_LISTEN_ADDR:-$control_addr:2377}"
current_addr="$(docker info --format '{{.Swarm.NodeAddr}}')"

if [[ "$current_addr" == "$control_addr" ]]; then
  echo "Swarm control-plane already advertises $control_addr"
  "$SCRIPT_DIR/init-manager.sh" "$control_addr"
  exit 0
fi

docker swarm init \
  --force-new-cluster \
  --advertise-addr "$control_addr" \
  --listen-addr "$listen_addr" \
  --data-path-addr "$data_path_addr"

"$SCRIPT_DIR/init-manager.sh" "$control_addr"

docker info --format 'NodeAddr={{.Swarm.NodeAddr}} Managers={{json .Swarm.RemoteManagers}}'
