#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
. "$SCRIPT_DIR/_common.sh"

load_env

if [[ "$(swarm_state)" == "active" ]]; then
  mapfile -t service_names < <(docker service ls --format '{{.Name}}')
  if [[ "${#service_names[@]}" -gt 0 ]]; then
    docker service rm "${service_names[@]}"
    for _ in $(seq 1 30); do
      if [[ -z "$(docker service ls -q)" ]]; then
        break
      fi
      sleep 1
    done
  fi

  mapfile -t node_rows < <(docker node ls --format '{{.ID}}|{{.Hostname}}|{{.Status}}|{{.ManagerStatus}}')
  self_id="$(manager_node_id)"

  for row in "${node_rows[@]}"; do
    node_id="${row%%|*}"
    rest="${row#*|}"
    hostname="${rest%%|*}"
    rest="${rest#*|}"
    status="${rest%%|*}"

    [[ "$node_id" == "$self_id" ]] && continue

    if [[ "$status" == "Down" ]]; then
      docker node rm --force "$node_id" || true
      continue
    fi

    docker node update --availability drain "$node_id" >/dev/null 2>&1 || true
    docker node rm "$node_id" >/dev/null 2>&1 || echo "Warning: unable to cleanly remove active worker $hostname before swarm reset." >&2
  done

  docker swarm leave --force
fi

docker rm -f "$REGISTRY_CONTAINER_NAME" >/dev/null 2>&1 || true
docker volume rm portainer_data registry_data >/dev/null 2>&1 || true

"$SCRIPT_DIR/init-manager.sh" "$SWARM_CONTROL_ADDR"
