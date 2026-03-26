#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from cccc.daemon.server import call_daemon


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise RuntimeError(f"template not found: {path}") from exc


def _call(op: str, args: dict[str, Any], *, timeout_s: float = 30.0) -> dict[str, Any]:
    payload = {"op": op, "args": args}
    try:
        response = call_daemon(payload, timeout_s=timeout_s)
    except Exception as exc:
        raise RuntimeError(f"daemon call failed for {op}: {exc}") from exc

    if not isinstance(response, dict):
        raise RuntimeError(f"{op} returned a non-dict response")

    if response.get("ok"):
        return response

    error = response.get("error") if isinstance(response.get("error"), dict) else {}
    code = str(error.get("code") or "daemon_error")
    message = str(error.get("message") or f"{op} failed")
    details = error.get("details")
    if details:
        raise RuntimeError(f"{code}: {message} | details={details}")
    raise RuntimeError(f"{code}: {message}")


def _create_group(args: argparse.Namespace) -> int:
    project_root = Path(args.project_root).expanduser().resolve()
    template_path = Path(args.template).expanduser().resolve()
    template_text = _read_text(template_path)
    response = _call(
        "group_create_from_template",
        {
            "path": str(project_root),
            "title": str(args.title or project_root.name),
            "topic": str(args.topic or ""),
            "by": str(args.by or "user"),
            "template": template_text,
        },
        timeout_s=60.0,
    )
    group_id = str(response.get("result", {}).get("group_id") or "").strip()
    if not group_id:
        raise RuntimeError("group_create_from_template returned an empty group_id")
    print(group_id)
    return 0


def _apply_template(args: argparse.Namespace) -> int:
    template_path = Path(args.template).expanduser().resolve()
    template_text = _read_text(template_path)
    group_id = str(args.group_id or "").strip()
    if not group_id:
        raise RuntimeError("group_id is required")
    _call(
        "group_template_import_replace",
        {
            "group_id": group_id,
            "confirm": group_id,
            "by": str(args.by or "user"),
            "template": template_text,
        },
        timeout_s=60.0,
    )
    print(group_id)
    return 0


def _preview_template(args: argparse.Namespace) -> int:
    template_path = Path(args.template).expanduser().resolve()
    template_text = _read_text(template_path)
    group_id = str(args.group_id or "").strip()
    if not group_id:
        raise RuntimeError("group_id is required")
    response = _call(
        "group_template_preview",
        {
            "group_id": group_id,
            "by": str(args.by or "user"),
            "template": template_text,
        },
        timeout_s=30.0,
    )
    print(json.dumps(response.get("result", {}), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create, preview, or apply the project CCCC 0.4.7 group template."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    create_parser = subparsers.add_parser("create", help="Create a new working group from the template")
    create_parser.add_argument("--project-root", required=True, help="Project root to attach as the working-group scope")
    create_parser.add_argument("--template", required=True, help="Path to the CCCC group template YAML")
    create_parser.add_argument("--title", default="", help="Working-group title")
    create_parser.add_argument("--topic", default="", help="Working-group topic")
    create_parser.add_argument("--by", default="user", help="Requester id")
    create_parser.set_defaults(func=_create_group)

    apply_parser = subparsers.add_parser("apply", help="Replace an existing working group with the template")
    apply_parser.add_argument("--group-id", required=True, help="Existing working-group id")
    apply_parser.add_argument("--template", required=True, help="Path to the CCCC group template YAML")
    apply_parser.add_argument("--by", default="user", help="Requester id")
    apply_parser.set_defaults(func=_apply_template)

    preview_parser = subparsers.add_parser("preview", help="Preview the template diff against an existing group")
    preview_parser.add_argument("--group-id", required=True, help="Existing working-group id")
    preview_parser.add_argument("--template", required=True, help="Path to the CCCC group template YAML")
    preview_parser.add_argument("--by", default="user", help="Requester id")
    preview_parser.set_defaults(func=_preview_template)

    return parser


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()
    try:
        return int(args.func(args))
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
