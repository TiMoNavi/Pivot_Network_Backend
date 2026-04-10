#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
. "$SCRIPT_DIR/_common.sh"

load_env

target_dir="$SWARM_DIR/upstream/portainer-compose"

if [[ -d "$target_dir/.git" ]]; then
  git -C "$target_dir" fetch --depth 1 origin "$PORTAINER_UPSTREAM_REF"
  git -C "$target_dir" checkout "$PORTAINER_UPSTREAM_REF"
  git -C "$target_dir" pull --ff-only origin "$PORTAINER_UPSTREAM_REF"
else
  git clone --depth 1 --branch "$PORTAINER_UPSTREAM_REF" "$PORTAINER_UPSTREAM_REPO" "$target_dir"
fi

git -C "$target_dir" rev-parse --short HEAD
