#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
. "$SCRIPT_DIR/common.sh"

load_env
ensure_local_registry

docker build \
  --tag pivot-backend-build-team/benchmark-worker:swarm-local \
  --file "$SWARM_DIR/benchmark_worker/Dockerfile" \
  "$SWARM_DIR/benchmark_worker"

docker tag \
  pivot-backend-build-team/benchmark-worker:swarm-local \
  "$BENCHMARK_SWARM_IMAGE"

docker push "$BENCHMARK_SWARM_IMAGE"
