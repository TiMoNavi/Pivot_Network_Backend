#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec bash "${SCRIPT_DIR}/run-windows-bootstrap.sh" "bootstrap/windows/monitor_swarm_manager_truth.ps1" "$@"
