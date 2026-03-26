from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

import psutil


REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "backend"
CACHE_DIR = REPO_ROOT / ".cache" / "e2e-local-web"
BACKEND_PORT = 8012
SELLER_PORT = 3848
BUYER_PORT = 3858
SELLER_STATE_DIR = REPO_ROOT / ".cache" / "seller-web-e2e-script"
BUYER_CODE_PATH = REPO_ROOT / ".cache" / "buyer-web-script-main.py"


def request_json(
    method: str,
    url: str,
    payload: dict[str, Any] | None = None,
    timeout: int = 120,
) -> dict[str, Any]:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {"Accept": "application/json"}
    if payload is not None:
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, method=method, headers=headers, data=data)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8")
            return {"ok": True, "status": response.status, "data": json.loads(body)}
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")
        try:
            parsed = json.loads(body)
        except json.JSONDecodeError:
            parsed = {"raw": body}
        return {"ok": False, "status": exc.code, "data": parsed}
    except urllib.error.URLError as exc:
        return {"ok": False, "status": None, "data": {"raw": str(exc)}}  # type: ignore[return-value]


def wait_for_health(url: str, timeout_seconds: int = 40) -> None:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        result = request_json("GET", url, timeout=5)
        if result["ok"]:
            return
        time.sleep(1)
    raise RuntimeError(f"health_check_timeout: {url}")


def start_process(command: list[str], cwd: Path, env: dict[str, str], stdout_path: Path, stderr_path: Path) -> subprocess.Popen[str]:
    stdout_path.parent.mkdir(parents=True, exist_ok=True)
    stdout_path.write_text("", encoding="utf-8")
    stderr_path.write_text("", encoding="utf-8")
    stdout_handle = open(stdout_path, "ab")
    stderr_handle = open(stderr_path, "ab")
    return subprocess.Popen(
        command,
        cwd=str(cwd),
        env=env,
        stdout=stdout_handle,
        stderr=stderr_handle,
    )


def stop_process(process: subprocess.Popen[str] | None) -> None:
    if process is None:
        return
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()


def run() -> dict[str, Any]:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    SELLER_STATE_DIR.mkdir(parents=True, exist_ok=True)
    BUYER_CODE_PATH.write_text("print('hello from buyer runtime')\nprint(6 * 7)\n", encoding="utf-8")

    backend_db = BACKEND_DIR / f"http_frontend_e2e_{int(time.time())}.sqlite3"

    seller_email = f"seller-web-{int(time.time())}@example.com"
    buyer_email = f"buyer-web-{int(time.time())}@example.com"
    password = "super-secret-password"

    backend_env = os.environ.copy()
    backend_env["DATABASE_URL"] = f"sqlite:///./{backend_db.name}"
    backend_env["CELERY_BROKER_URL"] = "redis://localhost:6379/0"
    backend_env["CELERY_RESULT_BACKEND"] = "redis://localhost:6379/0"

    processes: list[subprocess.Popen[str]] = []
    try:
        for port in (BACKEND_PORT, SELLER_PORT, BUYER_PORT):
            for conn in psutil.net_connections(kind="tcp"):
                if conn.laddr and conn.laddr.port == port and conn.status == "LISTEN" and conn.pid:
                    try:
                        os.kill(conn.pid, signal.SIGTERM)
                    except OSError:
                        pass
        time.sleep(2)

        backend_proc = start_process(
            ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", str(BACKEND_PORT)],
            BACKEND_DIR,
            backend_env,
            CACHE_DIR / "backend.stdout.log",
            CACHE_DIR / "backend.stderr.log",
        )
        processes.append(backend_proc)
        seller_proc = start_process(
            [
                sys.executable,
                "-c",
                (
                    "import uvicorn; from seller_client.agent_server import app; "
                    f"uvicorn.run(app, host='127.0.0.1', port={SELLER_PORT})"
                ),
            ],
            REPO_ROOT,
            os.environ.copy(),
            CACHE_DIR / "seller.stdout.log",
            CACHE_DIR / "seller.stderr.log",
        )
        processes.append(seller_proc)
        buyer_proc = start_process(
            [
                sys.executable,
                "-c",
                (
                    "import uvicorn; from buyer_client.agent_server import app; "
                    f"uvicorn.run(app, host='127.0.0.1', port={BUYER_PORT})"
                ),
            ],
            REPO_ROOT,
            os.environ.copy(),
            CACHE_DIR / "buyer.stdout.log",
            CACHE_DIR / "buyer.stderr.log",
        )
        processes.append(buyer_proc)

        wait_for_health(f"http://127.0.0.1:{BACKEND_PORT}/api/v1/health")
        wait_for_health(f"http://127.0.0.1:{SELLER_PORT}/api/health")
        wait_for_health(f"http://127.0.0.1:{BUYER_PORT}/api/health")

        seller_onboarding = request_json(
            "POST",
            f"http://127.0.0.1:{SELLER_PORT}/api/onboarding",
            {
                "intent": "我是新的 seller 节点，请从零开始把这台 Windows 机器接入平台，完成 runtime、WireGuard、Docker Swarm 接入并上报节点。",
                "email": seller_email,
                "password": password,
                "display_name": "Seller Web E2E",
                "backend_url": f"http://127.0.0.1:{BACKEND_PORT}",
                "state_dir": str(SELLER_STATE_DIR),
            },
            timeout=300,
        )
        if not seller_onboarding["ok"]:
            raise RuntimeError(f"seller_onboarding_failed: {seller_onboarding['data']}")

        seller_dashboard = request_json(
            "GET",
            f"http://127.0.0.1:{SELLER_PORT}/api/dashboard?state_dir={urllib.parse.quote(str(SELLER_STATE_DIR))}",
            timeout=120,
        )
        if not seller_dashboard["ok"]:
            raise RuntimeError(f"seller_dashboard_failed: {seller_dashboard['data']}")
        seller_node_key = (
            seller_onboarding["data"].get("result", {}).get("result", {}).get("node_id")
            or seller_onboarding["data"].get("result", {}).get("node_id")
        )
        if not seller_node_key:
            seller_nodes = seller_dashboard["data"]["platform"]["overview"]["nodes"]
            if not seller_nodes:
                raise RuntimeError("seller_node_not_found_after_onboarding")
            seller_node_key = seller_nodes[0]["node_key"]

        buyer_run = request_json(
            "POST",
            f"http://127.0.0.1:{BUYER_PORT}/api/runtime/run-code",
            {
                "backend_url": f"http://127.0.0.1:{BACKEND_PORT}",
                "email": buyer_email,
                "password": password,
                "seller_node_key": seller_node_key,
                "runtime_image": "python:3.12-alpine",
                "code_filename": BUYER_CODE_PATH.name,
                "code_content": BUYER_CODE_PATH.read_text(encoding="utf-8"),
            },
            timeout=120,
        )
        if not buyer_run["ok"]:
            raise RuntimeError(f"buyer_run_failed: {buyer_run['data']}")
        local_id = buyer_run["data"]["session"]["local_id"]

        deadline = time.time() + 180
        buyer_session: dict[str, Any] | None = None
        while time.time() < deadline:
            current = request_json(
                "GET",
                f"http://127.0.0.1:{BUYER_PORT}/api/runtime/sessions/{local_id}",
                timeout=120,
            )
            if not current["ok"]:
                raise RuntimeError(f"buyer_session_refresh_failed: {current['data']}")
            buyer_session = current["data"]["session"]
            if buyer_session["status"] in {"completed", "failed", "stopped"}:
                break
            time.sleep(2)
        if buyer_session is None:
            raise RuntimeError("buyer_session_poll_failed")
        if buyer_session["status"] != "completed":
            raise RuntimeError(f"buyer_session_not_completed: {buyer_session}")
        if "hello from buyer runtime" not in (buyer_session.get("logs") or ""):
            raise RuntimeError(f"buyer_logs_missing_expected_output: {buyer_session}")
        if "42" not in (buyer_session.get("logs") or ""):
            raise RuntimeError(f"buyer_logs_missing_expected_result: {buyer_session}")

        stop_result = request_json(
            "POST",
            f"http://127.0.0.1:{BUYER_PORT}/api/runtime/sessions/{local_id}/stop",
            {},
            timeout=120,
        )
        if not stop_result["ok"]:
            raise RuntimeError(f"buyer_stop_failed: {stop_result['data']}")

        return {
            "backend_url": f"http://127.0.0.1:{BACKEND_PORT}",
            "seller_local_web": f"http://127.0.0.1:{SELLER_PORT}",
            "buyer_local_web": f"http://127.0.0.1:{BUYER_PORT}",
            "seller_email": seller_email,
            "buyer_email": buyer_email,
            "seller_node_key": seller_node_key,
            "buyer_local_session_id": local_id,
            "buyer_session": buyer_session,
        }
    finally:
        for process in reversed(processes):
            stop_process(process)


def main() -> None:
    result = run()
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
