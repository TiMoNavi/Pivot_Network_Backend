#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
. "$SCRIPT_DIR/common.sh"

load_env
ensure_local_registry

docker build \
  --tag pivot-backend-build-team/backend:swarm-local \
  --file "$REPO_ROOT/backend/Dockerfile" \
  "$REPO_ROOT"

docker tag \
  pivot-backend-build-team/backend:swarm-local \
  "$BACKEND_SWARM_IMAGE"

docker push "$BACKEND_SWARM_IMAGE"
