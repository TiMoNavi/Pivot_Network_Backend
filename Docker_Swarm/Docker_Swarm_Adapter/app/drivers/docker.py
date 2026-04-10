from __future__ import annotations

import time
from typing import Any

from app.drivers.command import CommandExecutionError, CommandRunner, parse_json_lines, parse_json_output


class DockerDriver:
    def __init__(self, runner: CommandRunner) -> None:
        self.runner = runner

    def info(self) -> dict[str, Any]:
        output = self.runner.run(["docker", "info", "--format", "{{json .Swarm}}"])
        return parse_json_output(output)

    def node_ls(self) -> list[dict[str, Any]]:
        output = self.runner.run(["docker", "node", "ls", "--format", "{{json .}}"])
        return parse_json_lines(output)

    def service_ls(self) -> list[dict[str, Any]]:
        output = self.runner.run(["docker", "service", "ls", "--format", "{{json .}}"])
        return parse_json_lines(output)

    def node_inspect(self, node_ref: str) -> dict[str, Any]:
        output = self.runner.run(["docker", "node", "inspect", node_ref, "--format", "{{json .}}"])
        return parse_json_output(output)

    def node_ps(self, node_ref: str) -> list[dict[str, Any]]:
        output = self.runner.run(
            ["docker", "node", "ps", node_ref, "--no-trunc", "--format", "{{json .}}"]
        )
        return parse_json_lines(output)

    def service_inspect(self, service_ref: str) -> dict[str, Any]:
        output = self.runner.run(["docker", "service", "inspect", service_ref, "--format", "{{json .}}"])
        return parse_json_output(output)

    def service_ps(self, service_ref: str) -> list[dict[str, Any]]:
        output = self.runner.run(
            ["docker", "service", "ps", service_ref, "--no-trunc", "--format", "{{json .}}"]
        )
        return parse_json_lines(output)

    def service_logs(self, service_ref: str, tail: int = 20) -> str:
        return self.runner.run(
            ["docker", "service", "logs", "--raw", "--tail", str(tail), service_ref]
        )

    def image_pull(self, image_ref: str) -> str:
        return self.runner.run(["docker", "pull", image_ref])

    def image_inspect(self, image_ref: str) -> dict[str, Any]:
        output = self.runner.run(["docker", "image", "inspect", image_ref, "--format", "{{json .}}"])
        return parse_json_output(output)

    def run_container_check(
        self,
        image_ref: str,
        entrypoint: str,
        command: list[str],
    ) -> str:
        full_command = ["docker", "run", "--rm", "--entrypoint", entrypoint, image_ref]
        full_command.extend(command)
        return self.runner.run(full_command)

    def network_create(self, name: str, labels: dict[str, str] | None = None) -> dict[str, Any]:
        command = ["docker", "network", "create", "--driver", "overlay", "--scope", "swarm", "--attachable"]
        for key, value in (labels or {}).items():
            command.extend(["--label", f"{key}={value}"])
        command.append(name)
        self.runner.run(command)
        return self.network_inspect(name)

    def network_inspect(self, name: str) -> dict[str, Any]:
        output = self.runner.run(["docker", "network", "inspect", name, "--format", "{{json .}}"])
        return parse_json_output(output)

    def network_rm(self, name: str) -> None:
        self.runner.run(["docker", "network", "rm", name])

    def service_create(
        self,
        *,
        name: str,
        image: str,
        labels: dict[str, str] | None = None,
        container_labels: dict[str, str] | None = None,
        env: dict[str, str] | None = None,
        constraints: list[str] | None = None,
        networks: list[str] | None = None,
        args: list[str] | None = None,
        entrypoint: str | None = None,
        published_port: int | None = None,
        target_port: int | None = None,
        publish_mode: str = "ingress",
    ) -> dict[str, Any]:
        command = [
            "docker",
            "service",
            "create",
            "--detach",
            "--name",
            name,
            "--restart-condition",
            "none",
            "--no-resolve-image",
        ]
        for key, value in (labels or {}).items():
            command.extend(["--label", f"{key}={value}"])
        for key, value in (container_labels or {}).items():
            command.extend(["--container-label", f"{key}={value}"])
        for key, value in (env or {}).items():
            command.extend(["--env", f"{key}={value}"])
        for constraint in constraints or []:
            command.extend(["--constraint", constraint])
        for network in networks or []:
            command.extend(["--network", network])
        if entrypoint:
            command.extend(["--entrypoint", entrypoint])
        if published_port is not None and target_port is not None:
            command.extend(
                [
                    "--publish",
                    f"published={published_port},target={target_port},protocol=tcp,mode={publish_mode}",
                ]
            )
        command.append(image)
        command.extend(args or [])
        self.runner.run(command)
        return self.service_inspect(name)

    def service_rm(self, service_name: str) -> None:
        self.runner.run(["docker", "service", "rm", service_name])

    def service_exists(self, service_name: str) -> bool:
        try:
            self.service_inspect(service_name)
            return True
        except CommandExecutionError:
            return False

    def network_exists(self, network_name: str) -> bool:
        try:
            self.network_inspect(network_name)
            return True
        except CommandExecutionError:
            return False

    def wait_for_service_removal(self, service_name: str, attempts: int = 20, delay_seconds: float = 0.5) -> None:
        for _ in range(attempts):
            if not self.service_exists(service_name):
                return
            time.sleep(delay_seconds)

    def wait_for_network_removal(self, network_name: str, attempts: int = 20, delay_seconds: float = 0.5) -> None:
        for _ in range(attempts):
            if not self.network_exists(network_name):
                return
            time.sleep(delay_seconds)

    def swarm_join_token(self, role: str = "worker") -> str:
        return self.runner.run(["docker", "swarm", "join-token", "-q", role]).strip()

    def node_update_labels(
        self,
        node_id: str,
        add_labels: dict[str, str] | None = None,
        remove_labels: list[str] | None = None,
    ) -> dict[str, Any]:
        command = ["docker", "node", "update"]
        for label in remove_labels or []:
            command.extend(["--label-rm", label])
        for key, value in (add_labels or {}).items():
            command.extend(["--label-add", f"{key}={value}"])
        command.append(node_id)
        self.runner.run(command)
        return self.node_inspect(node_id)

    def node_update_availability(self, node_id: str, availability: str) -> dict[str, Any]:
        self.runner.run(["docker", "node", "update", "--availability", availability, node_id])
        return self.node_inspect(node_id)

    def node_rm(self, node_id: str, force: bool = False) -> None:
        command = ["docker", "node", "rm"]
        if force:
            command.append("--force")
        command.append(node_id)
        self.runner.run(command)

    def resolve_node_ref(self, node_ref: str) -> str:
        if node_ref == "self":
            return self.info().get("NodeID", "")

        candidates = self.node_ls()
        exact_matches = [
            node["ID"]
            for node in candidates
            if node.get("ID") == node_ref or node.get("Hostname") == node_ref
        ]
        if len(exact_matches) == 1:
            return exact_matches[0]
        if len(exact_matches) > 1:
            raise CommandExecutionError(["docker", "node", "ls"], f"ambiguous_node_ref: {node_ref}")

        prefix_matches = [node["ID"] for node in candidates if node.get("ID", "").startswith(node_ref)]
        if len(prefix_matches) == 1:
            return prefix_matches[0]
        if len(prefix_matches) > 1:
            raise CommandExecutionError(["docker", "node", "ls"], f"ambiguous_node_ref: {node_ref}")

        raise CommandExecutionError(["docker", "node", "ls"], f"unable_to_resolve_node_ref: {node_ref}")
