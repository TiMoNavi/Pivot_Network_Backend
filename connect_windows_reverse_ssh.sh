#!/usr/bin/env bash
set -euo pipefail
exec ssh win-local-via-reverse-ssh "$@"
