#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
. "$SCRIPT_DIR/common.sh"

load_env
require_swarm_active

worker_token="$(docker swarm join-token --quiet worker)"
manager_ip="$(manager_addr)"

cat <<EOF
Seller compute node onboarding

On the seller's Linux machine:
1. Install Docker Engine.
2. Allow pulls from this manager registry:
   REGISTRY_HOST=${REGISTRY_HOST} bash configure-registry-access.sh
3. Join the Swarm as a worker:
   docker swarm join --token ${worker_token} ${manager_ip}:2377

Back on the manager:
4. Find the new node name:
   docker node ls
5. Label it as a compute node:
   ./scripts/label-compute-node.sh <node-hostname> compute-node-001 seller-001 gpu

Recommended convention:
- one seller machine = one compute node
- manager stays control-plane only
- seller nodes get platform.role=compute and platform.compute_enabled=true
EOF
