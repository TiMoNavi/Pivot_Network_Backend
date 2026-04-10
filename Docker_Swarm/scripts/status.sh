#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
. "$SCRIPT_DIR/_common.sh"

load_env

echo "== docker info =="
docker info --format 'swarm_state={{.Swarm.LocalNodeState}} node_id={{.Swarm.NodeID}} node_addr={{.Swarm.NodeAddr}} control_available={{.Swarm.ControlAvailable}} nodes={{.Swarm.Nodes}} managers={{.Swarm.Managers}}'

echo
echo "== docker node ls =="
docker node ls

echo
echo "== docker stack ls =="
docker stack ls

echo
echo "== docker service ls =="
docker service ls

echo
echo "== docker volume ls =="
docker volume ls

echo
echo "== wg show =="
wg show || true

if [[ -d "$SWARM_DIR/upstream/portainer-compose/.git" ]]; then
  echo
  echo "== portainer upstream =="
  git -C "$SWARM_DIR/upstream/portainer-compose" rev-parse --short HEAD
fi
