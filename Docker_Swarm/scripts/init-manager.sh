#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
. "$SCRIPT_DIR/_common.sh"

load_env

advertise_addr="${1:-$SWARM_CONTROL_ADDR}"
data_path_addr="${SWARM_DATA_PATH_ADDR:-$advertise_addr}"
listen_addr="${SWARM_LISTEN_ADDR:-$advertise_addr:2377}"
state="$(swarm_state)"

if [[ "$state" != "active" ]]; then
  docker swarm init \
    --advertise-addr "$advertise_addr" \
    --listen-addr "$listen_addr" \
    --data-path-addr "$data_path_addr"
fi

node_id="$(manager_node_id)"
docker node update \
  --label-add platform.managed=true \
  --label-add platform.role=control-plane \
  --label-add platform.control_plane=true \
  --label-add platform.compute_enabled=false \
  --label-add "platform.manager_addr=$advertise_addr" \
  --label-add "platform.manager_public_addr=$SWARM_MANAGER_ADDR" \
  "$node_id" >/dev/null

docker node inspect "$node_id" --format 'hostname={{.Description.Hostname}} role={{.Spec.Role}} state={{.Status.State}} availability={{.Spec.Availability}} labels={{json .Spec.Labels}}'
