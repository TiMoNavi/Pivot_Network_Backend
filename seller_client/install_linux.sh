#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if ! command -v python >/dev/null 2>&1; then
  echo "Python is required to run the seller client installer skeleton." >&2
  exit 1
fi

echo "Running seller client installer skeleton (Linux)..."
python "$SCRIPT_DIR/installer.py" "$@"
