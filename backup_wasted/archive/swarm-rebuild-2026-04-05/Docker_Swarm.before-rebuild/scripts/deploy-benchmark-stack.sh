#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
. "$SCRIPT_DIR/common.sh"

load_env
require_swarm_active
ensure_local_registry

docker stack deploy \
  --resolve-image never \
  --compose-file "$SWARM_DIR/compose.benchmark.yml" \
  "$BENCHMARK_STACK_NAME"
