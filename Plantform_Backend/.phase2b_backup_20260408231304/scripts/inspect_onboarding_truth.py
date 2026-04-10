#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import os
from typing import Any

import httpx


def _request_json(client: httpx.Client, path: str, *, headers: dict[str, str] | None = None) -> dict[str, Any]:
    response = client.get(path, headers=headers)
    try:
        payload: Any = response.json()
    except ValueError:
        payload = {"raw": response.text}
    return {
        "path": path,
        "status_code": response.status_code,
        "ok": not response.is_error,
        "payload": payload,
    }


def _session_truth(session_response: dict[str, Any]) -> dict[str, Any]:
    if not session_response["ok"]:
        return session_response

    session = session_response["payload"]
    return {
        "path": session_response["path"],
        "status_code": session_response["status_code"],
        "session_id": session.get("session_id"),
        "status": session.get("status"),
        "seller_user_id": session.get("seller_user_id"),
        "requested_accelerator": session.get("requested_accelerator"),
        "requested_compute_node_id": session.get("requested_compute_node_id"),
        "expected_wireguard_ip": session.get("expected_wireguard_ip"),
        "required_labels": session.get("required_labels") or {},
        "swarm_join_material": {
            "manager_addr": (session.get("swarm_join_material") or {}).get("manager_addr"),
            "manager_port": (session.get("swarm_join_material") or {}).get("manager_port"),
            "recommended_compute_node_id": (session.get("swarm_join_material") or {}).get("recommended_compute_node_id"),
            "expected_wireguard_ip": (session.get("swarm_join_material") or {}).get("expected_wireguard_ip"),
            "claim_required": (session.get("swarm_join_material") or {}).get("claim_required"),
            "next_step": (session.get("swarm_join_material") or {}).get("next_step"),
        },
        "last_join_complete": session.get("last_join_complete"),
        "manager_acceptance": session.get("manager_acceptance"),
    }


def _swarm_overview_truth(overview_response: dict[str, Any]) -> dict[str, Any]:
    if not overview_response["ok"]:
        return overview_response

    overview = overview_response["payload"]
    return {
        "path": overview_response["path"],
        "status_code": overview_response["status_code"],
        "manager_host": overview.get("manager_host"),
        "swarm": overview.get("swarm"),
        "node_list_summary": overview.get("node_list_summary") or [],
        "service_list_summary": overview.get("service_list_summary") or [],
    }


def _node_detail_truth(node_response: dict[str, Any]) -> dict[str, Any]:
    if not node_response["ok"]:
        return node_response

    payload = node_response["payload"]
    return {
        "path": node_response["path"],
        "status_code": node_response["status_code"],
        "node": payload.get("node"),
        "platform_labels": payload.get("platform_labels") or {},
        "raw_labels": payload.get("raw_labels") or {},
        "tasks": payload.get("tasks") or [],
        "recent_error_summary": payload.get("recent_error_summary") or [],
    }


def _node_search_truth(search_response: dict[str, Any]) -> dict[str, Any]:
    if not search_response["ok"]:
        return search_response

    payload = search_response["payload"]
    return {
        "path": search_response["path"],
        "status_code": search_response["status_code"],
        "query": payload.get("query"),
        "total": payload.get("total"),
        "items": payload.get("items") or [],
        "applied_filters": payload.get("applied_filters") or {},
    }


def _clean_optional_string(value: Any) -> str | None:
    if value is None:
        return None
    cleaned = str(value).strip()
    return cleaned or None


def _derive_summary(report: dict[str, Any]) -> dict[str, Any]:
    session = report.get("session_truth")
    manager_acceptance = session.get("manager_acceptance") if isinstance(session, dict) else None
    last_join_complete = session.get("last_join_complete") if isinstance(session, dict) else None
    expected_wireguard_ip = _clean_optional_string((manager_acceptance or {}).get("expected_wireguard_ip")) or _clean_optional_string(
        session.get("expected_wireguard_ip") if isinstance(session, dict) else None
    )
    observed_manager_node_addr = _clean_optional_string((manager_acceptance or {}).get("observed_manager_node_addr"))
    observed_wireguard_ip = _clean_optional_string((last_join_complete or {}).get("observed_wireguard_ip"))

    swarm_overview = report.get("swarm_overview")
    node_list_summary = swarm_overview.get("node_list_summary") if isinstance(swarm_overview, dict) else []
    if not isinstance(node_list_summary, list):
        node_list_summary = []
    worker_nodes = [node for node in node_list_summary if str(node.get("role") or "").lower() == "worker"]

    search_results = report.get("operator_searches") or []
    search_hits = 0
    for item in search_results:
        if isinstance(item, dict) and "items" in item:
            search_hits += int(item.get("total") or 0)

    by_compute = report.get("operator_node_by_compute_node_id")
    by_ref = report.get("operator_node_by_ref")

    signals: list[str] = []
    if expected_wireguard_ip and observed_manager_node_addr and expected_wireguard_ip != observed_manager_node_addr:
        signals.append("manager_node_addr_mismatch")
    if expected_wireguard_ip and observed_wireguard_ip and expected_wireguard_ip == observed_wireguard_ip:
        signals.append("runtime_wireguard_matches_expected")
    if expected_wireguard_ip and not any(node.get("node_addr") == expected_wireguard_ip for node in worker_nodes):
        signals.append("no_worker_with_expected_wireguard_ip_in_swarm_overview")
    if not worker_nodes:
        signals.append("swarm_overview_has_no_worker_nodes")
    if search_hits == 0:
        signals.append("operator_searches_returned_no_hits")
    if isinstance(by_compute, dict) and not by_compute.get("ok", True):
        signals.append(f"by_compute_node_id_lookup_failed_{by_compute.get('status_code')}")
    if isinstance(by_ref, dict) and not by_ref.get("ok", True):
        signals.append(f"by_ref_lookup_failed_{by_ref.get('status_code')}")

    if "manager_node_addr_mismatch" in signals:
        interpretation = "manager_node_addr_mismatch_confirmed"
    elif "swarm_overview_has_no_worker_nodes" in signals:
        interpretation = "worker_absent_from_manager_control_plane"
    elif manager_acceptance and manager_acceptance.get("status") == "matched":
        interpretation = "manager_acceptance_matched"
    else:
        interpretation = "inspection_incomplete_or_pending"

    return {
        "interpretation": interpretation,
        "signals": signals,
        "session_status": session.get("status") if isinstance(session, dict) else None,
        "manager_acceptance_status": (manager_acceptance or {}).get("status"),
        "expected_wireguard_ip": expected_wireguard_ip,
        "observed_wireguard_ip": observed_wireguard_ip,
        "observed_manager_node_addr": observed_manager_node_addr,
        "search_hit_total": search_hits,
        "swarm_worker_count": len(worker_nodes),
        "swarm_node_total": ((swarm_overview or {}).get("swarm") or {}).get("nodes") if isinstance(swarm_overview, dict) else None,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Print a repo-owned correction report for seller onboarding session truth and operator-side corroboration."
    )
    parser.add_argument("--backend-base-url", default="http://127.0.0.1:8000", help="Backend base URL.")
    parser.add_argument("--api-prefix", default="/api/v1", help="Backend API prefix.")
    parser.add_argument("--session-id", help="Join session id to inspect.")
    parser.add_argument("--compute-node-id", help="Compute node id for operator-side corroboration.")
    parser.add_argument("--node-ref", help="Swarm node ref for operator-side corroboration.")
    parser.add_argument(
        "--bearer-token",
        help="Explicit backend bearer token for seller/admin protected session reads.",
    )
    parser.add_argument(
        "--bearer-token-env",
        help="Optional environment variable name holding a backend bearer token for seller/admin session reads.",
    )
    args = parser.parse_args()

    bearer_token = args.bearer_token or os.getenv("BACKEND_BEARER_TOKEN")

    report: dict[str, Any] = {
        "inputs": {
            "backend_base_url": args.backend_base_url,
            "api_prefix": args.api_prefix,
            "session_id": args.session_id,
            "compute_node_id": args.compute_node_id,
            "node_ref": args.node_ref,
            "bearer_token_supplied": bool(bearer_token),
            "bearer_token_env": args.bearer_token_env,
        },
        "session_truth": None,
        "swarm_overview": None,
        "operator_searches": [],
        "operator_node_by_compute_node_id": None,
        "operator_node_by_ref": None,
        "summary": None,
    }

    auth_headers: dict[str, str] | None = None
    if args.bearer_token_env and not bearer_token:
        token = os.getenv(args.bearer_token_env)
        if not token:
            raise SystemExit(f"Environment variable {args.bearer_token_env} is not set.")
        bearer_token = token

    if args.session_id and not bearer_token:
        raise SystemExit("--session-id requires --bearer-token, BACKEND_BEARER_TOKEN, or --bearer-token-env.")

    if bearer_token:
        auth_headers = {"Authorization": f"Bearer {bearer_token}"}

    with httpx.Client(base_url=args.backend_base_url, timeout=20.0) as client:
        api_prefix = args.api_prefix.rstrip("/")
        session_truth_payload: dict[str, Any] | None = None
        if args.session_id:
            session_response = _request_json(
                client,
                f"{api_prefix}/seller/onboarding/sessions/{args.session_id}",
                headers=auth_headers,
            )
            report["session_truth"] = _session_truth(session_response)
            if session_response["ok"]:
                session_truth_payload = session_response["payload"]

        report["swarm_overview"] = _swarm_overview_truth(_request_json(client, f"{api_prefix}/platform/swarm/overview"))

        effective_compute_node_id = _clean_optional_string(args.compute_node_id)
        if effective_compute_node_id is None and session_truth_payload is not None:
            effective_compute_node_id = (
                _clean_optional_string(((session_truth_payload.get("last_join_complete") or {}).get("compute_node_id")))
                or _clean_optional_string(((session_truth_payload.get("manager_acceptance") or {}).get("compute_node_id")))
                or _clean_optional_string(session_truth_payload.get("requested_compute_node_id"))
            )

        effective_node_ref = _clean_optional_string(args.node_ref)
        if effective_node_ref is None and session_truth_payload is not None:
            effective_node_ref = (
                _clean_optional_string(((session_truth_payload.get("last_join_complete") or {}).get("node_ref")))
                or _clean_optional_string(((session_truth_payload.get("manager_acceptance") or {}).get("node_ref")))
            )

        search_candidates: list[str] = []
        for value in (
            effective_compute_node_id,
            effective_node_ref,
            _clean_optional_string((session_truth_payload or {}).get("expected_wireguard_ip")),
            _clean_optional_string((((session_truth_payload or {}).get("manager_acceptance") or {}).get("observed_manager_node_addr"))),
            _clean_optional_string((((session_truth_payload or {}).get("last_join_complete") or {}).get("observed_wireguard_ip"))),
        ):
            if value and value not in search_candidates:
                search_candidates.append(value)

        for candidate in search_candidates:
            search_response = _request_json(client, f"{api_prefix}/platform/nodes/search?query={candidate}")
            report["operator_searches"].append(_node_search_truth(search_response))

        if effective_compute_node_id:
            report["inputs"]["compute_node_id"] = effective_compute_node_id
            report["operator_node_by_compute_node_id"] = _node_detail_truth(
                _request_json(client, f"{api_prefix}/platform/nodes/by-compute-node-id/{effective_compute_node_id}")
            )

        if effective_node_ref:
            report["inputs"]["node_ref"] = effective_node_ref
            report["operator_node_by_ref"] = _node_detail_truth(
                _request_json(client, f"{api_prefix}/platform/nodes/{effective_node_ref}")
            )

    report["summary"] = _derive_summary(report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
