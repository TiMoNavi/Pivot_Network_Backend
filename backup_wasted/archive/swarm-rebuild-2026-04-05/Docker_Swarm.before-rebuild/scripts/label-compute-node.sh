#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
. "$SCRIPT_DIR/common.sh"

require_swarm_active

if [[ $# -lt 3 ]]; then
  echo "Usage: $0 <node_id_or_hostname> <compute_node_id> <seller_user_id> [accelerator]" >&2
  exit 1
fi

node_id="$1"
compute_node_id="$2"
seller_user_id="$3"
accelerator="${4:-gpu}"
resolved_node_id="$(resolve_node_ref "$node_id")"
hostname="$(node_hostname "$resolved_node_id")"
status="$(node_status "$resolved_node_id")"
role="$(node_role "$resolved_node_id")"
current_seller_user_id="$(node_label "$resolved_node_id" "platform.seller_user_id")"
current_compute_node_id="$(node_label "$resolved_node_id" "platform.compute_node_id")"

if is_control_plane_node "$resolved_node_id"; then
  echo "Refusing to claim control-plane/manager node $hostname." >&2
  exit 1
fi

if [[ "$role" != "worker" ]]; then
  echo "Refusing to claim non-worker node $hostname (role=$role)." >&2
  exit 1
fi

if [[ "$status" != "ready" ]]; then
  echo "Refusing to claim node $hostname because swarm status is $status, not ready." >&2
  exit 1
fi

if [[ -n "$current_seller_user_id" && "$current_seller_user_id" != "$seller_user_id" ]]; then
  echo "Refusing to change seller_user_id on claimed node $hostname: current=$current_seller_user_id requested=$seller_user_id." >&2
  exit 1
fi

if [[ -n "$current_compute_node_id" && "$current_compute_node_id" != "$compute_node_id" ]]; then
  echo "Refusing to change compute_node_id on claimed node $hostname: current=$current_compute_node_id requested=$compute_node_id." >&2
  exit 1
fi

if conflicting_node_id="$(find_node_with_compute_node_id "$compute_node_id" "$resolved_node_id")"; then
  echo "Refusing duplicate compute_node_id=$compute_node_id; already present on $(node_hostname "$conflicting_node_id")." >&2
  exit 1
fi

docker node update \
  --label-add platform.managed=true \
  --label-add platform.role=compute \
  --label-add platform.control_plane=false \
  --label-add platform.compute_enabled=true \
  --label-add "platform.compute_node_id=${compute_node_id}" \
  --label-add "platform.seller_user_id=${seller_user_id}" \
  --label-add "platform.accelerator=${accelerator}" \
  "$resolved_node_id"

docker node inspect "$resolved_node_id" --format 'hostname={{.Description.Hostname}} role={{.Spec.Role}} state={{.Status.State}} availability={{.Spec.Availability}} labels={{json .Spec.Labels}}'
