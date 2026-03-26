#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import socket
import sys
import time
from pathlib import Path
from typing import Any

from cccc.daemon.server import get_daemon_endpoint


READY_MARKERS = (
    "Booting MCP server: cccc",
    "Use /skills to list available skills",
    "gpt-5.4",
    "Write tests for @filename",
)
TRUST_MARKER = "Do you trust the contents of this directory?"


def _connect_term_socket(group_id: str, actor_id: str) -> tuple[socket.socket, socket.SocketIO]:
    endpoint = get_daemon_endpoint()
    transport = str(endpoint.get("transport") or "").strip().lower()
    if transport == "tcp":
        sock = socket.create_connection(
            (str(endpoint.get("host") or "127.0.0.1"), int(endpoint.get("port") or 0)),
            timeout=10,
        )
    else:
        path = str(endpoint.get("path") or "")
        if not path:
            raise RuntimeError("daemon unix socket path is empty")
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(10)
        sock.connect(path)

    stream = sock.makefile("rwb", buffering=0)
    request = {"op": "term_attach", "args": {"group_id": group_id, "actor_id": actor_id}}
    stream.write((json.dumps(request, ensure_ascii=False) + "\n").encode("utf-8"))
    line = stream.readline()
    try:
        response = json.loads(line.decode("utf-8", errors="replace"))
    except Exception as exc:
        raise RuntimeError(f"invalid term_attach response: {line!r}") from exc
    if not isinstance(response, dict) or not response.get("ok"):
        error = response.get("error") if isinstance(response.get("error"), dict) else {}
        code = str(error.get("code") or "term_attach_failed")
        message = str(error.get("message") or "term_attach failed")
        raise RuntimeError(f"{code}: {message}")
    return sock, stream


def _read_until_ready(sock: socket.socket, *, trust_timeout_s: float, ready_timeout_s: float) -> str:
    sock.settimeout(1.0)
    chunks: list[bytes] = []
    deadline = time.time() + trust_timeout_s
    trust_sent = False

    while time.time() < deadline:
        try:
            data = sock.recv(8192)
        except TimeoutError:
            continue
        if not data:
            raise RuntimeError("terminal closed before startup prompt was ready")
        chunks.append(data)
        text = b"".join(chunks).decode("utf-8", errors="replace")
        if (not trust_sent) and TRUST_MARKER in text:
            sock.sendall(b"1")
            time.sleep(0.3)
            sock.sendall(b"\r")
            trust_sent = True
            break
        if any(marker in text for marker in READY_MARKERS):
            return text

    deadline = time.time() + ready_timeout_s
    while time.time() < deadline:
        try:
            data = sock.recv(8192)
        except TimeoutError:
            continue
        if not data:
            raise RuntimeError("terminal closed before actor reached ready state")
        chunks.append(data)
        text = b"".join(chunks).decode("utf-8", errors="replace")
        if any(marker in text for marker in READY_MARKERS):
            return text

    return b"".join(chunks).decode("utf-8", errors="replace")


def _wait_for_reply(
    ledger_path: Path,
    *,
    actor_id: str,
    nonce: str,
    timeout_s: float,
) -> dict[str, Any]:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if ledger_path.exists():
            lines = ledger_path.read_text(encoding="utf-8").splitlines()[-200:]
            for line in lines:
                if not line.strip():
                    continue
                try:
                    event = json.loads(line)
                except Exception:
                    continue
                if event.get("kind") != "chat.message":
                    continue
                if str(event.get("by") or "") != actor_id:
                    continue
                text = str((event.get("data") or {}).get("text") or "")
                if nonce in text:
                    return event
        time.sleep(2)
    raise RuntimeError("actor did not reply before timeout")


def main() -> int:
    parser = argparse.ArgumentParser(description="Attach to a CCCC actor terminal, auto-accept trust, and verify a reply.")
    parser.add_argument("--group-id", required=True)
    parser.add_argument("--actor-id", required=True)
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--cccc-home", default=os.environ.get("CCCC_HOME", ""))
    parser.add_argument("--trust-timeout-seconds", type=float, default=8.0)
    parser.add_argument("--ready-timeout-seconds", type=float, default=12.0)
    parser.add_argument("--reply-timeout-seconds", type=float, default=180.0)
    args = parser.parse_args()

    cccc_home = str(args.cccc_home or "").strip()
    if cccc_home:
        os.environ["CCCC_HOME"] = cccc_home

    project_root = Path(args.project_root).expanduser().resolve()
    ledger_path = Path(os.environ["CCCC_HOME"]) / "groups" / str(args.group_id).strip() / "ledger.jsonl"

    nonce = f"startup{int(time.time()) % 1_000_000:06d}"
    prompt = (
        f"Reply to the user via CCCC MCP right now with exactly: CCCC startup OK {nonce}. "
        "Do not say anything else."
    )

    sock: socket.socket | None = None
    stream: socket.SocketIO | None = None
    try:
        sock, stream = _connect_term_socket(str(args.group_id), str(args.actor_id))
        _read_until_ready(
            sock,
            trust_timeout_s=float(args.trust_timeout_seconds),
            ready_timeout_s=float(args.ready_timeout_seconds),
        )
        sock.sendall(prompt.encode("utf-8"))
        time.sleep(0.3)
        sock.sendall(b"\r")
        reply_event = _wait_for_reply(
            ledger_path,
            actor_id=str(args.actor_id),
            nonce=nonce,
            timeout_s=float(args.reply_timeout_seconds),
        )
    finally:
        try:
            if stream is not None:
                stream.close()
        except Exception:
            pass
        try:
            if sock is not None:
                sock.close()
        except Exception:
            pass

    payload = {
        "actor_id": str(args.actor_id),
        "nonce": nonce,
        "reply_event_id": str(reply_event.get("id") or ""),
        "reply_by": str(reply_event.get("by") or ""),
        "reply_text": str((reply_event.get("data") or {}).get("text") or ""),
    }
    print(json.dumps(payload, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
