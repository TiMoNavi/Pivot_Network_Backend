#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
. "$SCRIPT_DIR/_common.sh"

load_env

archive_dir="${1:-$ARCHIVE_ROOT/swarm-rebuild-$(date +%F)}"

mkdir -p "$archive_dir/state" "$archive_dir/systemd" "$archive_dir/wireguard" "$archive_dir/snapshots"

docker info > "$archive_dir/state/docker-info.txt"
docker node ls > "$archive_dir/state/docker-node-ls.txt" || true
docker service ls > "$archive_dir/state/docker-service-ls.txt" || true
docker volume ls > "$archive_dir/state/docker-volume-ls.txt"
docker ps -a > "$archive_dir/state/docker-ps-a.txt"
docker stack ls > "$archive_dir/state/docker-stack-ls.txt" || true

if [[ "$(swarm_state)" == "active" ]]; then
  docker node inspect "$(manager_node_id)" > "$archive_dir/state/docker-node-inspect-self.json"
  docker node inspect "$(manager_node_id)" --format '{{json .Spec.Labels}}' > "$archive_dir/state/manager-labels.json"
fi

cp -a /etc/systemd/system/pivot-swarm-adapter.service "$archive_dir/systemd/" 2>/dev/null || true
wg show > "$archive_dir/wireguard/wg-show.txt" || true
ls -la /etc/wireguard > "$archive_dir/wireguard/etc-wireguard-ls.txt" 2>/dev/null || true
cp -a /etc/wireguard/archive/. "$archive_dir/wireguard/" 2>/dev/null || true

find /root/Pivot_network/Docker_Swarm -maxdepth 4 | sort > "$archive_dir/snapshots/docker-swarm-tree.txt" 2>/dev/null || true
find /root/Pivot_network/Portainer -maxdepth 4 | sort > "$archive_dir/snapshots/portainer-tree.txt" 2>/dev/null || true
find /root/Pivot_network/Docker_Swarm_Adapter -maxdepth 4 | sort > "$archive_dir/snapshots/docker-swarm-adapter-tree.txt" 2>/dev/null || true
ls -la /root/Pivot_network > "$archive_dir/snapshots/pivot-network-top-level.txt"

echo "$archive_dir"
