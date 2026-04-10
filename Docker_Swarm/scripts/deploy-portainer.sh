#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
. "$SCRIPT_DIR/_common.sh"

load_env
ensure_swarm_active

docker stack deploy \
  --compose-file "$SWARM_DIR/stack/portainer-agent-stack.yml" \
  "$PORTAINER_STACK_NAME"

docker stack services "$PORTAINER_STACK_NAME"
