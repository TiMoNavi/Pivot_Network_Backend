from __future__ import annotations

import tempfile
from pathlib import Path

from app.drivers.command import CommandExecutionError, CommandRunner


class WireGuardDriver:
    def __init__(self, runner: CommandRunner, interface: str, config_path: Path) -> None:
        self.runner = runner
        self.interface = interface
        self.config_path = config_path

    def show(self) -> str:
        return self.runner.run(["wg", "show"])

    def read_config(self) -> str:
        return self.config_path.read_text(encoding="utf-8")

    def interface_exists(self) -> bool:
        try:
            output = self.show()
        except CommandExecutionError:
            return False
        return f"interface: {self.interface}" in output

    def set_peer(
        self,
        public_key: str,
        allowed_ips: list[str],
        persistent_keepalive: int | None = None,
        endpoint: str | None = None,
    ) -> None:
        command = ["wg", "set", self.interface, "peer", public_key, "allowed-ips", ",".join(allowed_ips)]
        if persistent_keepalive is not None:
            command.extend(["persistent-keepalive", str(persistent_keepalive)])
        if endpoint:
            command.extend(["endpoint", endpoint])
        self.runner.run(command)

    def remove_peer(self, public_key: str) -> None:
        self.runner.run(["wg", "set", self.interface, "peer", public_key, "remove"])

    def write_config(self, content: str) -> None:
        tmp_dir = self.config_path.parent
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=tmp_dir, delete=False) as handle:
            handle.write(content)
            tmp_path = Path(handle.name)
        tmp_path.chmod(0o600)
        tmp_path.replace(self.config_path)
