#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"

# shellcheck disable=SC1091
. "$REPO_ROOT/Docker_Swarm/scripts/common.sh"

load_env
require_swarm_active
ensure_local_registry
cache_image_in_local_registry portainer/agent:lts "$PORTAINER_AGENT_IMAGE"
cache_image_in_local_registry portainer/portainer-ce:lts "$PORTAINER_SERVER_IMAGE"

docker stack deploy \
  --resolve-image never \
  --compose-file "$SCRIPT_DIR/compose.portainer.yml" \
  "$PORTAINER_STACK_NAME"
