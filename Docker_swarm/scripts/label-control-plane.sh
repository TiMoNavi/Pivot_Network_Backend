#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
. "$SCRIPT_DIR/common.sh"

require_swarm_active

node_id="${1:-self}"
manager_ip="${2:-$(manager_addr)}"
resolved_node_id="$(resolve_node_ref "$node_id")"

docker node update \
  --label-add platform.managed=true \
  --label-add platform.role=control-plane \
  --label-add platform.control_plane=true \
  --label-add platform.compute_enabled=false \
  --label-add "platform.manager_addr=${manager_ip}" \
  "$resolved_node_id"

docker node inspect "$resolved_node_id" --format '{{json .Spec.Labels}}'
