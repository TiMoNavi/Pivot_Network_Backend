#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
. "$SCRIPT_DIR/common.sh"

load_env

registry_host="${1:-$REGISTRY_HOST}"

docker run --rm \
  --privileged \
  -v /:/host \
  python:3.13-alpine \
  sh -lc "python - '$registry_host' <<'PY'
import json
import sys
from pathlib import Path

registry_host = sys.argv[1]
daemon_path = Path('/host/etc/docker/daemon.json')
if daemon_path.exists():
    data = json.loads(daemon_path.read_text(encoding='utf-8'))
else:
    data = {}

insecure = data.setdefault('insecure-registries', [])
if registry_host not in insecure:
    insecure.append(registry_host)

daemon_path.write_text(json.dumps(data, indent=4) + '\n', encoding='utf-8')
print(json.dumps(data, indent=2))
PY"

docker run --rm \
  --privileged \
  --pid=host \
  debian:bookworm-slim \
  sh -lc "nsenter -t 1 -m -u -i -n -p -- systemctl restart docker" || true

for _ in $(seq 1 30); do
  if docker info >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

docker info | sed -n '/Insecure Registries:/,/Live Restore Enabled:/p'
