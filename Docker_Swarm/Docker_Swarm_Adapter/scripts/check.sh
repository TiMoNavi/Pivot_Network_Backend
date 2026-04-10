#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd)"

cd "$PROJECT_DIR"
set -a
. "$PROJECT_DIR/.env"
set +a
. "$PROJECT_DIR/.venv/bin/activate"

python -m compileall app >/dev/null
python - <<'PY'
import subprocess
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

health = client.get("/health")
assert health.status_code == 200, health.text
payload = health.json()
assert payload["status"] == "ok"

unauth = client.get("/swarm/overview")
assert unauth.status_code == 401, unauth.text
body = unauth.json()
assert body["error_code"] == "adapter_auth_failed", body

headers = {"Authorization": f"Bearer {__import__('os').environ['ADAPTER_TOKEN']}"}

probe = client.post("/swarm/nodes/probe", json={"node_ref": "self"}, headers=headers)
assert probe.status_code == 200, probe.text
probe_payload = probe.json()
assert probe_payload["probe_status"] in {"probed", "probe_failed"}

search_nodes = client.get(
    "/swarm/nodes/search",
    params={"query": "self"},
    headers=headers,
)
assert search_nodes.status_code == 200, search_nodes.text
search_payload = search_nodes.json()
assert "nodes" in search_payload, search_payload
assert "total" in search_payload, search_payload

detail_by_ref = client.get("/swarm/nodes/by-ref/self", headers=headers)
assert detail_by_ref.status_code == 200, detail_by_ref.text
detail_payload = detail_by_ref.json()
assert detail_payload["node"]["id"], detail_payload

join_material = client.post(
    "/swarm/nodes/join-material",
    json={
        "seller_user_id": "seller-self-test",
        "requested_accelerator": "gpu",
        "expected_wireguard_ip": "10.66.66.10",
    },
    headers=headers,
)
assert join_material.status_code == 200, join_material.text
join_payload = join_material.json()
assert join_payload["expected_wireguard_ip"] == "10.66.66.10", join_payload

service = client.post(
    "/swarm/services/inspect",
    json={"service_name": "portainer_portainer"},
    headers=headers,
)
assert service.status_code == 200, service.text
service_payload = service.json()
assert service_payload["service_name"] == "portainer_portainer"

validate = client.post(
    "/swarm/runtime-images/validate",
    json={"image_ref": "portainer/agent:lts", "node_ref": "self"},
    headers=headers,
)
assert validate.status_code == 200, validate.text
validate_payload = validate.json()
assert validate_payload["validation_status"] in {"validated", "validation_failed"}, validate_payload

bundle = client.post(
    "/swarm/runtime-session-bundles/create",
    json={
        "session_id": "session-self-test",
        "offer_id": "offer-self-test",
        "node_ref": "self",
        "runtime_image_ref": "portainer/agent:lts",
        "requested_duration_minutes": 30,
        "buyer_user_id": "buyer-self-test",
        "network_mode": "wireguard",
    },
    headers=headers,
)
assert bundle.status_code == 400, bundle.text

private_key = subprocess.check_output(["wg", "genkey"], text=True).strip()
public_key = subprocess.run(
    ["wg", "pubkey"],
    input=private_key + "\n",
    text=True,
    capture_output=True,
    check=True,
).stdout.strip()

apply = client.post(
    "/wireguard/peers/apply",
    headers=headers,
    json={
        "lease_type": "buyer_test",
        "runtime_session_id": "runtime-session-test",
        "peer_payload": {
            "public_key": public_key,
        },
    },
)
assert apply.status_code == 200, apply.text
remove = client.post(
    "/wireguard/peers/remove",
    headers=headers,
    json={
        "lease_type": "buyer_test",
        "runtime_session_id": "runtime-session-test",
    },
)
assert remove.status_code == 200, remove.text

print("adapter checks passed")
PY
