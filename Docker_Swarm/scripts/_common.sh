#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SWARM_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd)"
ENV_FILE="${ENV_FILE:-$SWARM_DIR/env/swarm.env}"

load_env() {
  if [[ -f "$ENV_FILE" ]]; then
    set -a
    # shellcheck disable=SC1090
    . "$ENV_FILE"
    set +a
  fi

  export SWARM_MANAGER_ADDR="${SWARM_MANAGER_ADDR:-81.70.52.75}"
  export SWARM_CONTROL_ADDR="${SWARM_CONTROL_ADDR:-$SWARM_MANAGER_ADDR}"
  export SWARM_DATA_PATH_ADDR="${SWARM_DATA_PATH_ADDR:-$SWARM_CONTROL_ADDR}"
  export SWARM_LISTEN_ADDR="${SWARM_LISTEN_ADDR:-$SWARM_CONTROL_ADDR:2377}"
  export PORTAINER_STACK_NAME="${PORTAINER_STACK_NAME:-portainer}"
  export PORTAINER_AGENT_IMAGE="${PORTAINER_AGENT_IMAGE:-portainer/agent:lts}"
  export PORTAINER_SERVER_IMAGE="${PORTAINER_SERVER_IMAGE:-portainer/portainer-ce:lts}"
  export PORTAINER_UPSTREAM_REPO="${PORTAINER_UPSTREAM_REPO:-https://github.com/portainer/portainer-compose.git}"
  export PORTAINER_UPSTREAM_REF="${PORTAINER_UPSTREAM_REF:-master}"
  export REGISTRY_CONTAINER_NAME="${REGISTRY_CONTAINER_NAME:-pivot-swarm-registry}"
  export ARCHIVE_ROOT="${ARCHIVE_ROOT:-/root/Pivot_network/archive}"
}

swarm_state() {
  docker info --format '{{.Swarm.LocalNodeState}}'
}

ensure_swarm_active() {
  if [[ "$(swarm_state)" != "active" ]]; then
    echo "Docker Swarm is not active on this host." >&2
    exit 1
  fi
}

manager_node_id() {
  docker info --format '{{.Swarm.NodeID}}'
}

timestamp() {
  date +%Y-%m-%d-%H%M%S
}
