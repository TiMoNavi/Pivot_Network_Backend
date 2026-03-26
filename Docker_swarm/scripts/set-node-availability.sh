#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
. "$SCRIPT_DIR/common.sh"

require_swarm_active

if [[ $# -ne 2 ]]; then
  echo "Usage: $0 <node_id_or_hostname> <active|drain>" >&2
  exit 1
fi

node_ref="$1"
desired_availability="${2,,}"

case "$desired_availability" in
  active|drain)
    ;;
  *)
    echo "Unsupported availability: $desired_availability. Allowed values: active, drain." >&2
    exit 1
    ;;
esac

resolved_node_id="$(resolve_node_ref "$node_ref")"
hostname="$(node_hostname "$resolved_node_id")"
role="$(node_role "$resolved_node_id")"
status="$(node_status "$resolved_node_id")"
current_availability="$(node_availability "$resolved_node_id")"

if is_control_plane_node "$resolved_node_id"; then
  if [[ "$current_availability" == "$desired_availability" ]]; then
    echo "Control-plane node $hostname already availability=$current_availability. No mutation performed."
    docker node inspect "$resolved_node_id" --format 'hostname={{.Description.Hostname}} role={{.Spec.Role}} state={{.Status.State}} availability={{.Spec.Availability}}'
    exit 0
  fi

  echo "Refusing to mutate availability on control-plane/manager node $hostname." >&2
  exit 1
fi

if [[ "$role" != "worker" ]]; then
  echo "Refusing to mutate non-worker node $hostname (role=$role)." >&2
  exit 1
fi

if [[ "$status" != "ready" && "$current_availability" != "$desired_availability" ]]; then
  echo "Refusing to mutate node $hostname because swarm status is $status, not ready." >&2
  exit 1
fi

if [[ "$current_availability" == "$desired_availability" ]]; then
  echo "Node $hostname already availability=$current_availability. No mutation performed."
  docker node inspect "$resolved_node_id" --format 'hostname={{.Description.Hostname}} role={{.Spec.Role}} state={{.Status.State}} availability={{.Spec.Availability}}'
  exit 0
fi

if [[ "$desired_availability" == "drain" ]]; then
  ensure_no_running_replicated_tasks "$resolved_node_id"
fi

docker node update --availability "$desired_availability" "$resolved_node_id" >/dev/null
docker node inspect "$resolved_node_id" --format 'hostname={{.Description.Hostname}} role={{.Spec.Role}} state={{.Status.State}} availability={{.Spec.Availability}} labels={{json .Spec.Labels}}'
