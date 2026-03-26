#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
. "$SCRIPT_DIR/common.sh"

load_env
require_swarm_active

echo "== swarm =="
docker info --format 'state={{.Swarm.LocalNodeState}} node_addr={{.Swarm.NodeAddr}} control={{.Swarm.ControlAvailable}}'

echo "== nodes =="
docker node ls
echo "== node labels =="
docker node inspect $(docker node ls -q) --format '{{.Description.Hostname}} {{json .Spec.Labels}}'

if docker stack ls --format '{{.Name}}' | grep -qx "$STACK_NAME"; then
  echo "== app stack =="
  docker stack services "$STACK_NAME"
fi

if docker stack ls --format '{{.Name}}' | grep -qx "$PORTAINER_STACK_NAME"; then
  echo "== portainer stack =="
  docker stack services "$PORTAINER_STACK_NAME"
fi

if docker stack ls --format '{{.Name}}' | grep -qx "$BENCHMARK_STACK_NAME"; then
  echo "== benchmark stack =="
  docker stack services "$BENCHMARK_STACK_NAME"
fi
