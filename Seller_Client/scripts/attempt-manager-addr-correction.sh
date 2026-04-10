#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec bash "${SCRIPT_DIR}/run-windows-bootstrap.sh" "bootstrap/windows/attempt_manager_addr_correction_cycle.ps1" "$@"
