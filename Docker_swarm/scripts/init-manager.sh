#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
. "$SCRIPT_DIR/common.sh"

state="$(docker info --format '{{.Swarm.LocalNodeState}}')"
advertise_addr="${1:-}"

if [[ "$state" == "active" ]]; then
  echo "Docker Swarm is already active."
  echo "Manager address: $(manager_addr)"
  exit 0
fi

if [[ -z "$advertise_addr" ]]; then
  echo "Usage: $0 <manager_lan_ip>" >&2
  exit 1
fi

docker swarm init --advertise-addr "$advertise_addr"
echo "Docker Swarm initialized."
echo "Manager address: $(manager_addr)"
