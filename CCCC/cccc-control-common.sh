#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
PROJECT_ROOT=$(cd -- "${SCRIPT_DIR}/.." && pwd)
CCCC_DIR="${PROJECT_ROOT}/.cccc"
CONTROL_DIR="${CCCC_CONTROL_DIR:-${CCCC_DIR}/runtime/control}"
LOG_DIR="${CONTROL_DIR}/logs"
GROUP_ID_FILE="${CONTROL_DIR}/group.id"
WEB_PID_FILE="${CONTROL_DIR}/web.pid"
WEB_LOG_FILE="${LOG_DIR}/web.log"
WEB_PORT="${CCCC_WEB_PORT:-8848}"
WEB_HOST="${CCCC_WEB_HOST:-0.0.0.0}"
GROUP_TITLE="${CCCC_GROUP_TITLE:-Pivot Backend Build Team}"
GROUP_TOPIC="${CCCC_GROUP_TOPIC:-Phase 1 - AI-operated Docker Swarm adapter and backend compatibility layer}"
GROUP_TEMPLATE_PATH="${CCCC_GROUP_TEMPLATE_PATH:-${PROJECT_ROOT}/CCCC/templates/pivot-backend-build-team.group-template.yaml}"
GROUP_TEMPLATE_APPLIER="${PROJECT_ROOT}/CCCC/apply_group_template.py"
PYTHON_BIN="${PYTHON_BIN:-$(command -v python3)}"
SS_BIN="${SS_BIN:-$(command -v ss || true)}"
REQUIRED_ACTORS=(lead swarm_cli backend_adapter verification docs_summary)

normalize_terminal_env() {
  export TERM="${CCCC_TERM_OVERRIDE:-xterm-256color}"
  export COLORTERM="${COLORTERM:-truecolor}"
  export TERM_PROGRAM="${TERM_PROGRAM:-cccc}"
  export CLICOLOR="${CLICOLOR:-1}"
  export CLICOLOR_FORCE="${CLICOLOR_FORCE:-1}"
}

ensure_control_dirs() {
  mkdir -p "${CONTROL_DIR}" "${LOG_DIR}"
}

cccc_cmd() {
  if [[ -n "${CCCC_BIN:-}" ]]; then
    "${CCCC_BIN}" "$@"
    return
  fi
  "${SCRIPT_DIR}/run-cccc.sh" cccc "$@"
}

template_cmd() {
  if [[ ! -f "${GROUP_TEMPLATE_PATH}" ]]; then
    echo "Missing CCCC group template: ${GROUP_TEMPLATE_PATH}" >&2
    return 1
  fi
  if [[ ! -f "${GROUP_TEMPLATE_APPLIER}" ]]; then
    echo "Missing CCCC group template helper: ${GROUP_TEMPLATE_APPLIER}" >&2
    return 1
  fi
  "${SCRIPT_DIR}/run-cccc.sh" "${PYTHON_BIN}" "${GROUP_TEMPLATE_APPLIER}" "$@"
}

load_saved_group_id() {
  if [[ ! -f "${GROUP_ID_FILE}" ]]; then
    return 1
  fi
  tr -d '[:space:]' < "${GROUP_ID_FILE}"
}

save_group_id() {
  printf '%s\n' "$1" > "${GROUP_ID_FILE}"
}

group_exists() {
  local group_id=$1
  cccc_cmd groups | "${PYTHON_BIN}" -c '
import json
import sys

group_id = sys.argv[1]
payload = json.load(sys.stdin)
groups = payload.get("result", {}).get("groups", [])
raise SystemExit(0 if any(item.get("group_id") == group_id for item in groups) else 1)
' "$group_id"
}

find_group_by_title() {
  cccc_cmd groups | "${PYTHON_BIN}" -c '
import json
import sys

title = sys.argv[1]
payload = json.load(sys.stdin)
groups = payload.get("result", {}).get("groups", [])
for item in groups:
    if item.get("title") == title:
        print(item.get("group_id", ""))
        raise SystemExit(0)
raise SystemExit(1)
' "${GROUP_TITLE}"
}

create_group() {
  template_cmd create \
    --project-root "${PROJECT_ROOT}" \
    --template "${GROUP_TEMPLATE_PATH}" \
    --title "${GROUP_TITLE}" \
    --topic "${GROUP_TOPIC}"
}

discover_existing_group_id() {
  local group_id
  if group_id=$(load_saved_group_id 2>/dev/null); then
    if [[ -n "${group_id}" ]] && group_exists "${group_id}"; then
      printf '%s\n' "${group_id}"
      return 0
    fi
  fi
  if group_id=$(find_group_by_title 2>/dev/null); then
    if [[ -n "${group_id}" ]]; then
      printf '%s\n' "${group_id}"
      return 0
    fi
  fi
  return 1
}

resolve_group_id() {
  local group_id
  if group_id=$(discover_existing_group_id 2>/dev/null); then
    printf '%s\n' "${group_id}"
    return 0
  fi
  group_id=$(create_group)
  printf '%s\n' "${group_id}"
}

ensure_group_active() {
  cccc_cmd use "$1" >/dev/null
}

ensure_group_attached() {
  cccc_cmd attach --group "$1" "${PROJECT_ROOT}" >/dev/null
}

sync_group_metadata() {
  local group_id=$1
  cccc_cmd group update \
    --group "${group_id}" \
    --title "${GROUP_TITLE}" \
    --topic "${GROUP_TOPIC}" \
    >/dev/null
}

apply_group_template() {
  local group_id=$1
  template_cmd apply \
    --group-id "${group_id}" \
    --template "${GROUP_TEMPLATE_PATH}" \
    >/dev/null
}

actor_exists() {
  local group_id=$1
  local actor_id=$2
  cccc_cmd actor list --group "${group_id}" | "${PYTHON_BIN}" -c '
import json
import sys

actor_id = sys.argv[1]
payload = json.load(sys.stdin)
actors = payload.get("result", {}).get("actors", [])
raise SystemExit(0 if any(item.get("id") == actor_id for item in actors) else 1)
' "${actor_id}"
}

ensure_required_actors() {
  local group_id=$1
  local actor_id
  for actor_id in "${REQUIRED_ACTORS[@]}"; do
    if ! actor_exists "${group_id}" "${actor_id}"; then
      echo "missing required actor ${actor_id} for group ${group_id}" >&2
      return 1
    fi
  done
}

start_group_and_actors() {
  local group_id=$1
  local actor_id
  cccc_cmd group start --group "${group_id}" >/dev/null
  for actor_id in "${REQUIRED_ACTORS[@]}"; do
    cccc_cmd actor start "${actor_id}" --group "${group_id}" >/dev/null
  done
}

actors_healthy() {
  local group_id=$1
  cccc_cmd actor list --group "${group_id}" | "${PYTHON_BIN}" -c '
import json
import sys

required = sys.argv[1:]
payload = json.load(sys.stdin)
actors = {
    item.get("id"): item
    for item in payload.get("result", {}).get("actors", [])
}
for actor_id in required:
    actor = actors.get(actor_id)
    if actor is None or not actor.get("running"):
        raise SystemExit(1)
' "${REQUIRED_ACTORS[@]}"
}

wait_for_actor_health() {
  local group_id=$1
  local attempt
  for attempt in $(seq 1 20); do
    if actors_healthy "${group_id}"; then
      return 0
    fi
    sleep 0.5
  done
  return 1
}

is_web_listening() {
  if [[ -n "${SS_BIN}" ]]; then
    "${SS_BIN}" -ltn 2>/dev/null | grep -F ":${WEB_PORT} " >/dev/null
    return $?
  fi

  "${PYTHON_BIN}" - "${WEB_PORT}" "${WEB_HOST}" <<'PY'
import socket
import sys

port = int(sys.argv[1])
host = sys.argv[2]
if host in {"0.0.0.0", "::"}:
    host = "127.0.0.1"
sock = socket.socket()
sock.settimeout(0.5)
try:
    raise SystemExit(0 if sock.connect_ex((host, port)) == 0 else 1)
finally:
    sock.close()
PY
}

wait_for_web() {
  local attempt
  for attempt in $(seq 1 20); do
    if is_web_listening; then
      return 0
    fi
    sleep 0.5
  done
  return 1
}

launch_web_background() {
  if [[ -n "${CCCC_WEB_BIN:-}" ]]; then
    nohup "${CCCC_WEB_BIN}" >>"${WEB_LOG_FILE}" 2>&1 &
  else
    nohup "${SCRIPT_DIR}/run-cccc.sh" cccc web --host "${WEB_HOST}" --port "${WEB_PORT}" >>"${WEB_LOG_FILE}" 2>&1 &
  fi
  printf '%s\n' "$!" > "${WEB_PID_FILE}"
}

stop_managed_web() {
  local pid
  local attempt

  if [[ ! -f "${WEB_PID_FILE}" ]]; then
    return 0
  fi

  pid=$(tr -d '[:space:]' < "${WEB_PID_FILE}")
  if [[ -n "${pid}" ]] && kill -0 "${pid}" 2>/dev/null; then
    kill "${pid}" 2>/dev/null || true
    for attempt in $(seq 1 20); do
      if ! kill -0 "${pid}" 2>/dev/null; then
        break
      fi
      sleep 0.25
    done
    if kill -0 "${pid}" 2>/dev/null; then
      kill -9 "${pid}" 2>/dev/null || true
    fi
  fi

  rm -f "${WEB_PID_FILE}"
}
