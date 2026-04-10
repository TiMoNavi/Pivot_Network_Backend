#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
. "$SCRIPT_DIR/common.sh"

load_env

container_name="${1:-$LOCAL_SELLER_CONTAINER_NAME}"
node_name="${2:-$LOCAL_SELLER_NODE_NAME}"

if docker inspect "$container_name" >/dev/null 2>&1; then
  docker exec "$container_name" docker swarm leave --force >/dev/null 2>&1 || true
fi

docker node rm --force "$node_name" >/dev/null 2>&1 || true
docker rm -f "$container_name" >/dev/null 2>&1 || true
docker volume rm "$LOCAL_SELLER_DOCKER_VOLUME" >/dev/null 2>&1 || true
