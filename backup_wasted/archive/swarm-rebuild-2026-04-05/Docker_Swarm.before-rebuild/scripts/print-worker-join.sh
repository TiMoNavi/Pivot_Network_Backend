#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
. "$SCRIPT_DIR/common.sh"

require_swarm_active

token="$(docker swarm join-token --quiet worker)"
addr="$(manager_addr)"

echo "docker swarm join --token $token $addr:2377"
