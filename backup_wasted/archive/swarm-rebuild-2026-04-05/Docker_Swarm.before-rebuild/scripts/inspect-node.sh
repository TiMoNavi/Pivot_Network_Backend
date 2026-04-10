#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
. "$SCRIPT_DIR/common.sh"

require_swarm_active

if [[ $# -ne 1 ]]; then
  echo "Usage: $0 <node_id_or_hostname>" >&2
  exit 1
fi

resolved_node_id="$(resolve_node_ref "$1")"

echo "== node summary =="
docker node inspect "$resolved_node_id" --format 'id={{.ID}} hostname={{.Description.Hostname}} role={{.Spec.Role}} state={{.Status.State}} availability={{.Spec.Availability}}'

echo "== platform labels =="
docker node inspect "$resolved_node_id" --format 'platform.role={{index .Spec.Labels "platform.role"}} platform.control_plane={{index .Spec.Labels "platform.control_plane"}} platform.compute_enabled={{index .Spec.Labels "platform.compute_enabled"}} platform.compute_node_id={{index .Spec.Labels "platform.compute_node_id"}} platform.seller_user_id={{index .Spec.Labels "platform.seller_user_id"}} platform.accelerator={{index .Spec.Labels "platform.accelerator"}}'

echo "== raw labels =="
docker node inspect "$resolved_node_id" --format '{{json .Spec.Labels}}'

echo "== node tasks =="
docker node ps "$resolved_node_id" --format 'name={{.Name}} desired={{.DesiredState}} current={{.CurrentState}} error={{.Error}}'
