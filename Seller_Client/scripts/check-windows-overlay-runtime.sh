#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec bash "${SCRIPT_DIR}/run-windows-bootstrap.sh" "bootstrap/windows/check_windows_overlay_runtime.ps1" "$@"
