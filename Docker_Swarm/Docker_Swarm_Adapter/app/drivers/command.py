from __future__ import annotations

import json
import subprocess
from typing import Any


class CommandExecutionError(Exception):
    def __init__(self, command: list[str], message: str, exit_code: int | None = None) -> None:
        super().__init__(message)
        self.command = command
        self.message = message
        self.exit_code = exit_code


class CommandRunner:
    def __init__(self, timeout_seconds: int) -> None:
        self.timeout_seconds = timeout_seconds

    def run(self, command: list[str]) -> str:
        try:
            completed = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
            )
        except subprocess.TimeoutExpired as exc:
            raise CommandExecutionError(command, f"command_timeout: {exc}") from exc

        if completed.returncode != 0:
            raise CommandExecutionError(
                command,
                completed.stderr.strip() or completed.stdout.strip() or "command_failed",
                exit_code=completed.returncode,
            )

        return completed.stdout.strip()


def parse_json_output(output: str) -> Any:
    return json.loads(output) if output else {}


def parse_json_lines(output: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in output.splitlines():
        line = line.strip()
        if not line:
            continue
        rows.append(json.loads(line))
    return rows
