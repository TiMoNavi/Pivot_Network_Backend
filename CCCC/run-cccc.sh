#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
ROOT_DIR=$(cd -- "${SCRIPT_DIR}/.." && pwd)
CCCC_DIR="${ROOT_DIR}/.cccc"
WRAPPER_DIR="${CCCC_DIR}/bin"
PROJECT_CCCC_HOME="${CCCC_DIR}/runtime/cccc-home"
CCCC_REAL_BIN="${CCCC_REAL_BIN:-}"

REAL_CODEX="${CODEX_REAL_BIN:-}"
if [[ -z "${REAL_CODEX}" ]]; then
  REAL_CODEX=$(command -v codex || true)
fi

if [[ -z "${REAL_CODEX}" ]]; then
  echo "Could not find the real codex binary in PATH." >&2
  exit 127
fi

if [[ -z "${CCCC_REAL_BIN}" ]]; then
  if command -v cccc >/dev/null 2>&1; then
    CCCC_REAL_BIN="$(command -v cccc)"
  else
    for candidate in \
      "/home/cw/.local/bin/cccc" \
      "/home/cw/miniforge3/envs/cccc/bin/cccc" \
      "/home/cw/miniforge3/envs/py312/bin/cccc"
    do
      if [[ -x "${candidate}" ]]; then
        CCCC_REAL_BIN="${candidate}"
        break
      fi
    done
  fi
fi

if [[ -z "${CCCC_REAL_BIN}" ]]; then
  echo "Could not find the real cccc binary in PATH or standard local locations." >&2
  exit 127
fi

mkdir -p "${PROJECT_CCCC_HOME}"

if [[ $# -eq 0 ]]; then
  set -- "${CCCC_REAL_BIN}"
elif [[ "${1}" == "cccc" ]]; then
  shift
  set -- "${CCCC_REAL_BIN}" "$@"
fi

export TERM="${CCCC_TERM_OVERRIDE:-xterm-256color}"
export COLORTERM="${COLORTERM:-truecolor}"
export TERM_PROGRAM="${TERM_PROGRAM:-cccc}"
export CODEX_REAL_BIN="${REAL_CODEX}"
export CCCC_REAL_BIN="${CCCC_REAL_BIN}"
export CCCC_HOME="${PROJECT_CCCC_HOME}"
export PATH="${WRAPPER_DIR}:${PATH}"

exec "$@"
