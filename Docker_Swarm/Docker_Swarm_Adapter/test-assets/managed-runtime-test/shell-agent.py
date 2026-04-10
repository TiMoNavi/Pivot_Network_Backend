import json
import os
import subprocess
import tempfile
import zipfile
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse


WORKSPACE_ROOT = Path("/workspace")
WORKSPACE_ROOT.mkdir(parents=True, exist_ok=True)


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path in {"/", "/health"}:
            self._write_json(200, {"status": "ok", "service": "pivot-shell-agent"})
            return
        if parsed.path == "/shell/":
            body = f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <title>Pivot Runtime Shell</title>
    <style>
      body {{ font-family: monospace; margin: 24px; background: #0f172a; color: #e2e8f0; }}
      input, button {{ font: inherit; padding: 10px 12px; }}
      pre {{ background: #020617; border: 1px solid #1e293b; padding: 16px; min-height: 240px; white-space: pre-wrap; }}
    </style>
  </head>
  <body>
    <h1>Pivot Runtime Shell</h1>
    <p>Workspace: {WORKSPACE_ROOT}</p>
    <form id="shell-form">
      <input id="command" value="pwd && ls -la" size="60" />
      <button type="submit">Run</button>
    </form>
    <pre id="output"></pre>
    <script>
      document.getElementById('shell-form').addEventListener('submit', async (event) => {{
        event.preventDefault();
        const command = document.getElementById('command').value;
        const response = await fetch('/api/exec', {{
          method: 'POST',
          headers: {{ 'Content-Type': 'application/json' }},
          body: JSON.stringify({{ command }})
        }});
        const payload = await response.json();
        document.getElementById('output').textContent = JSON.stringify(payload, null, 2);
      }});
    </script>
  </body>
</html>
""".encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if parsed.path == "/api/workspace/status":
            files = []
            for path in WORKSPACE_ROOT.rglob("*"):
                if path.is_file():
                    files.append({"path": str(path.relative_to(WORKSPACE_ROOT)), "size": path.stat().st_size})
            self._write_json(200, {"workspace_root": str(WORKSPACE_ROOT), "files": files[:500]})
            return
        self._write_json(404, {"detail": "not_found"})

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/exec":
            payload = self._read_json()
            command = str(payload.get("command") or "").strip()
            if not command:
                self._write_json(400, {"detail": "command_required"})
                return
            completed = subprocess.run(
                ["/bin/sh", "-lc", command],
                cwd=str(WORKSPACE_ROOT),
                capture_output=True,
                text=True,
                timeout=120,
                check=False,
            )
            self._write_json(
                200,
                {
                    "exit_code": completed.returncode,
                    "stdout": completed.stdout,
                    "stderr": completed.stderr,
                    "workspace_root": str(WORKSPACE_ROOT),
                },
            )
            return
        if parsed.path == "/api/workspace/upload":
            raw_body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
            if not raw_body:
                self._write_json(400, {"detail": "body_required"})
                return
            temp_dir = Path(tempfile.mkdtemp(prefix="pivot-workspace-"))
            archive_path = temp_dir / "workspace.zip"
            archive_path.write_bytes(raw_body)
            self._write_json(200, {"status": "uploaded", "archive_path": str(archive_path)})
            return
        if parsed.path == "/api/workspace/extract":
            payload = self._read_json()
            archive_path = Path(str(payload.get("archive_path") or ""))
            if not archive_path.exists():
                self._write_json(404, {"detail": "archive_not_found"})
                return
            with zipfile.ZipFile(archive_path, "r") as archive:
                archive.extractall(WORKSPACE_ROOT)
            self._write_json(200, {"status": "extracted", "workspace_root": str(WORKSPACE_ROOT)})
            return
        self._write_json(404, {"detail": "not_found"})

    def _read_json(self):
        content_length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(content_length)
        return json.loads(raw.decode("utf-8") or "{}")

    def _write_json(self, status_code, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        return


server = HTTPServer(("0.0.0.0", 7681), Handler)
server.serve_forever()
