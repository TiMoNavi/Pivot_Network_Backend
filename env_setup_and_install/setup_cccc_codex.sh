#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
CODEX_DIR="${HOME}/.codex"
CODEX_CONFIG_TEMPLATE="${SCRIPT_DIR}/codex.config.toml"
START_GROUP="${START_GROUP:-0}"
LOCAL_CCCC_DIR="${REPO_ROOT}/.cccc"
LOCAL_CCCC_HOME="${LOCAL_CCCC_DIR}/home"
LOCAL_CCCC_HELP="${REPO_ROOT}/CCCC_HELP.md"

require_cmd() {
  local cmd="$1"
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "Missing required command: $cmd" >&2
    exit 1
  fi
}

json_field() {
  local field_path="$1"
  python3 -c '
import json
import sys

field_path = sys.argv[1].split(".")
doc = json.load(sys.stdin)
cur = doc
for key in field_path:
    if not isinstance(cur, dict):
        sys.exit(1)
    cur = cur.get(key)
    if cur is None:
        sys.exit(1)
print(cur)
' "$field_path"
}

actor_runtime() {
  local group_id="$1"
  local actor_id="$2"
  cccc actor list --group "$group_id" | python3 -c '
import json
import sys

actor_id = sys.argv[1]
doc = json.load(sys.stdin)
actors = doc.get("result", {}).get("actors", [])
for actor in actors:
    if str(actor.get("id") or "").strip() == actor_id:
        print(str(actor.get("runtime") or "").strip())
        sys.exit(0)
sys.exit(1)
' "$actor_id"
}

actor_role() {
  local group_id="$1"
  local actor_id="$2"
  cccc actor list --group "$group_id" | python3 -c '
import json
import sys

actor_id = sys.argv[1]
doc = json.load(sys.stdin)
actors = doc.get("result", {}).get("actors", [])
for actor in actors:
    if str(actor.get("id") or "").strip() == actor_id:
        print(str(actor.get("role") or "").strip())
        sys.exit(0)
sys.exit(1)
' "$actor_id"
}

actor_count() {
  local group_id="$1"
  cccc actor list --group "$group_id" | python3 -c '
import json
import sys

doc = json.load(sys.stdin)
actors = doc.get("result", {}).get("actors", [])
print(len(actors))
'
}

ensure_auth() {
  mkdir -p "$CODEX_DIR"
  if [ -f "${CODEX_DIR}/auth.json" ]; then
    return 0
  fi
  if [ -z "${OPENAI_API_KEY:-}" ]; then
    echo "Missing ${CODEX_DIR}/auth.json and OPENAI_API_KEY is not set." >&2
    echo "Create ~/.codex/auth.json or export OPENAI_API_KEY before rerunning." >&2
    exit 1
  fi
  cat > "${CODEX_DIR}/auth.json" <<EOF
{
  "OPENAI_API_KEY": "${OPENAI_API_KEY}"
}
EOF
  chmod 600 "${CODEX_DIR}/auth.json"
}

ensure_actor() {
  local group_id="$1"
  local actor_id="$2"
  local title="$3"
  local runtime
  if runtime="$(actor_runtime "$group_id" "$actor_id" 2>/dev/null)"; then
    if [ "$runtime" != "codex" ]; then
      cccc actor update "$actor_id" --group "$group_id" --runtime codex --enabled 1 --title "$title" >/dev/null
    else
      cccc actor update "$actor_id" --group "$group_id" --enabled 1 --title "$title" >/dev/null
    fi
    return 0
  fi
  cccc actor add "$actor_id" --group "$group_id" --runtime codex --title "$title" >/dev/null
}

sync_group_help() {
  local group_id="$1"
  local prompts_dir="${CCCC_HOME}/groups/${group_id}/prompts"
  mkdir -p "$prompts_dir"
  install -m 600 "$LOCAL_CCCC_HELP" "${prompts_dir}/CCCC_HELP.md"
}

require_cmd python3
require_cmd codex

python3 -m pip install -U cccc-pair

mkdir -p "$LOCAL_CCCC_HOME"
export CCCC_HOME="$LOCAL_CCCC_HOME"

mkdir -p "$CODEX_DIR"
install -m 600 "$CODEX_CONFIG_TEMPLATE" "${CODEX_DIR}/config.toml"
ensure_auth

cccc setup --runtime codex --path "$REPO_ROOT" >/dev/null

GROUP_ID="$(cccc attach "$REPO_ROOT" | json_field "result.group_id")"
cccc group use "$GROUP_ID" >/dev/null

# cccc-pair 0.4.9 reserves the actor id "foreman"; the first enabled actor
# still becomes the foreman role automatically.
if ! actor_runtime "$GROUP_ID" lead >/dev/null 2>&1; then
  if actor_runtime "$GROUP_ID" reviewer >/dev/null 2>&1; then
    if [ "$(actor_count "$GROUP_ID")" = "1" ] && [ "$(actor_role "$GROUP_ID" reviewer)" = "foreman" ]; then
      cccc group stop >/dev/null 2>&1 || true
      cccc actor remove reviewer --group "$GROUP_ID" >/dev/null
    fi
  fi
fi

ensure_actor "$GROUP_ID" lead Foreman
ensure_actor "$GROUP_ID" platform "Platform Backend"
ensure_actor "$GROUP_ID" buyer "Buyer Client"
ensure_actor "$GROUP_ID" runtime "Runtime & Swarm"
ensure_actor "$GROUP_ID" reviewer Reviewer
ensure_actor "$GROUP_ID" scribe "State & Docs"
ensure_actor "$GROUP_ID" tester "Windows & Test Operator"
sync_group_help "$GROUP_ID"

if [ "$START_GROUP" = "1" ]; then
  cccc group start >/dev/null
else
  cccc group stop >/dev/null 2>&1 || true
fi

echo "CCCC configured for ${REPO_ROOT}"
echo "CCCC_HOME: ${CCCC_HOME}"
echo "Group: ${GROUP_ID}"
echo "Actors: lead, platform, buyer, runtime, reviewer, scribe, tester"
echo "Runtime: codex"
if [ "$START_GROUP" = "1" ]; then
  echo "Status: started"
else
  echo "Status: configured and stopped"
  echo "Next: cccc group start"
fi
