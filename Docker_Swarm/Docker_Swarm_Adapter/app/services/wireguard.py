from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass

from app.config import Settings
from app.drivers.command import CommandExecutionError
from app.drivers.wireguard import WireGuardDriver
from app.errors import AdapterHTTPException
from app.schemas.wireguard import WireGuardPeerApplyRequest, WireGuardPeerRemoveRequest, WireGuardPeerResponse


@dataclass
class ParsedPeer:
    comments: list[str]
    public_key: str
    allowed_ips: list[str]
    endpoint: str | None
    persistent_keepalive: int | None
    block_lines: list[str]


class WireGuardService:
    def __init__(self, settings: Settings, wireguard: WireGuardDriver) -> None:
        self.settings = settings
        self.wireguard = wireguard

    def apply_peer(self, request: WireGuardPeerApplyRequest) -> WireGuardPeerResponse:
        payload = request.peer_payload or {}
        public_key = str(payload.get("public_key") or "").strip()
        if not public_key:
            raise AdapterHTTPException(400, "public_key_required", "wireguard_invalid_request")

        config_text = self.wireguard.read_config()
        interface_block, peers = self._parse_config(config_text)

        existing_for_session = self._find_peer_for_session(peers, request.runtime_session_id, request.lease_type)
        if existing_for_session and existing_for_session.public_key != public_key:
            raise AdapterHTTPException(409, "runtime_session_lease_already_exists", "wireguard_conflict")

        duplicate_key = self._find_peer_by_public_key(peers, public_key)
        if duplicate_key and not existing_for_session:
            raise AdapterHTTPException(409, "wireguard_public_key_already_exists", "wireguard_conflict")

        network = self._interface_network(interface_block)
        existing_ips = self._existing_client_ips(peers, network)
        client_address = str(payload.get("client_address") or "").strip()
        if not client_address:
            client_address = self._allocate_client_address(network, existing_ips)
        allowed_ips = payload.get("allowed_ips") or [f"{client_address}/32"]
        if isinstance(allowed_ips, str):
            allowed_ips = [item.strip() for item in allowed_ips.split(",") if item.strip()]
        persistent_keepalive = int(payload.get("persistent_keepalive", 25))
        endpoint = payload.get("endpoint")

        comments = [
            f"# pivot.runtime_session_id={request.runtime_session_id}",
            f"# pivot.lease_type={request.lease_type}",
        ]
        new_block = [
            "[Peer]",
            *comments,
            f"PublicKey = {public_key}",
            f"AllowedIPs = {', '.join(allowed_ips)}",
            f"PersistentKeepalive = {persistent_keepalive}",
        ]
        if endpoint:
            new_block.insert(-1, f"Endpoint = {endpoint}")

        if existing_for_session:
            peers = [peer for peer in peers if peer is not existing_for_session]

        peers.append(
            ParsedPeer(
                comments=comments,
                public_key=public_key,
                allowed_ips=list(allowed_ips),
                endpoint=endpoint,
                persistent_keepalive=persistent_keepalive,
                block_lines=new_block,
            )
        )

        self.wireguard.set_peer(
            public_key=public_key,
            allowed_ips=list(allowed_ips),
            persistent_keepalive=persistent_keepalive,
            endpoint=endpoint,
        )
        self.wireguard.write_config(self._render_config(interface_block, peers))

        metadata = self._interface_metadata(interface_block)
        client_allowed_ips = [f"{metadata['server_access_ip']}/32"] if metadata.get("server_access_ip") else []
        return WireGuardPeerResponse(
            runtime_session_id=request.runtime_session_id,
            lease_type=request.lease_type,
            status="applied",
            public_key=public_key,
            client_address=client_address,
            server_interface=self.settings.wireguard_interface,
            server_public_key=metadata["server_public_key"],
            server_access_ip=metadata["server_access_ip"],
            endpoint_host=metadata["endpoint_host"],
            endpoint_port=metadata["endpoint_port"],
            allowed_ips=list(allowed_ips),
            client_allowed_ips=client_allowed_ips,
            persistent_keepalive=persistent_keepalive,
            lease_payload={
                "runtime_session_id": request.runtime_session_id,
                "lease_type": request.lease_type,
                "client_address": client_address,
                "allowed_ips": list(allowed_ips),
                "client_allowed_ips": client_allowed_ips,
            },
        )

    def remove_peer(self, request: WireGuardPeerRemoveRequest) -> WireGuardPeerResponse:
        config_text = self.wireguard.read_config()
        interface_block, peers = self._parse_config(config_text)
        existing = self._find_peer_for_session(peers, request.runtime_session_id, request.lease_type)
        if existing is None:
            raise AdapterHTTPException(404, "wireguard_lease_not_found", "wireguard_not_found")

        try:
            self.wireguard.remove_peer(existing.public_key)
        except CommandExecutionError as exc:
            raise AdapterHTTPException(409, exc.message, "wireguard_remove_failed") from exc

        peers = [peer for peer in peers if peer is not existing]
        self.wireguard.write_config(self._render_config(interface_block, peers))

        metadata = self._interface_metadata(interface_block)
        client_allowed_ips = [f"{metadata['server_access_ip']}/32"] if metadata.get("server_access_ip") else []
        client_address = None
        if existing.allowed_ips:
            first_allowed = existing.allowed_ips[0]
            client_address = first_allowed.split("/", 1)[0]

        return WireGuardPeerResponse(
            runtime_session_id=request.runtime_session_id,
            lease_type=request.lease_type,
            status="removed",
            public_key=existing.public_key,
            client_address=client_address,
            server_interface=self.settings.wireguard_interface,
            server_public_key=metadata["server_public_key"],
            server_access_ip=metadata["server_access_ip"],
            endpoint_host=metadata["endpoint_host"],
            endpoint_port=metadata["endpoint_port"],
            allowed_ips=existing.allowed_ips,
            client_allowed_ips=client_allowed_ips,
            persistent_keepalive=existing.persistent_keepalive,
            lease_payload={
                "runtime_session_id": request.runtime_session_id,
                "lease_type": request.lease_type,
                "client_allowed_ips": client_allowed_ips,
            },
        )

    def get_peer(self, runtime_session_id: str, lease_type: str) -> WireGuardPeerResponse | None:
        config_text = self.wireguard.read_config()
        interface_block, peers = self._parse_config(config_text)
        existing = self._find_peer_for_session(peers, runtime_session_id, lease_type)
        if existing is None:
            return None

        metadata = self._interface_metadata(interface_block)
        client_allowed_ips = [f"{metadata['server_access_ip']}/32"] if metadata.get("server_access_ip") else []
        client_address = None
        if existing.allowed_ips:
            client_address = existing.allowed_ips[0].split("/", 1)[0]

        return WireGuardPeerResponse(
            runtime_session_id=runtime_session_id,
            lease_type=lease_type,
            status="applied",
            public_key=existing.public_key,
            client_address=client_address,
            server_interface=self.settings.wireguard_interface,
            server_public_key=metadata["server_public_key"],
            server_access_ip=metadata["server_access_ip"],
            endpoint_host=metadata["endpoint_host"],
            endpoint_port=metadata["endpoint_port"],
            allowed_ips=existing.allowed_ips,
            client_allowed_ips=client_allowed_ips,
            persistent_keepalive=existing.persistent_keepalive,
            lease_payload={
                "runtime_session_id": runtime_session_id,
                "lease_type": lease_type,
                "client_allowed_ips": client_allowed_ips,
            },
        )

    @staticmethod
    def _parse_config(config_text: str) -> tuple[list[str], list[ParsedPeer]]:
        lines = config_text.splitlines()
        interface_block: list[str] = []
        peer_blocks: list[list[str]] = []
        current_peer: list[str] = []
        pending_comments: list[str] = []
        in_peer = False

        for line in lines:
            stripped = line.strip()
            if stripped.startswith("#") and not in_peer:
                pending_comments.append(line)
                continue
            if stripped == "[Peer]":
                if current_peer:
                    peer_blocks.append(current_peer)
                current_peer = pending_comments + [line]
                pending_comments = []
                in_peer = True
                continue

            if in_peer:
                current_peer.append(line)
            else:
                if pending_comments:
                    interface_block.extend(pending_comments)
                    pending_comments = []
                interface_block.append(line)

        if current_peer:
            peer_blocks.append(current_peer)
        elif pending_comments:
            interface_block.extend(pending_comments)

        peers: list[ParsedPeer] = []
        for block in peer_blocks:
            comments = [line for line in block if line.strip().startswith("#")]
            public_key = ""
            allowed_ips: list[str] = []
            endpoint = None
            persistent_keepalive = None
            for line in block:
                stripped = line.strip()
                if stripped.startswith("PublicKey ="):
                    public_key = stripped.split("=", 1)[1].strip()
                elif stripped.startswith("AllowedIPs ="):
                    allowed_ips = [item.strip() for item in stripped.split("=", 1)[1].split(",") if item.strip()]
                elif stripped.startswith("Endpoint ="):
                    endpoint = stripped.split("=", 1)[1].strip()
                elif stripped.startswith("PersistentKeepalive ="):
                    persistent_keepalive = int(stripped.split("=", 1)[1].strip())
            if public_key:
                peers.append(
                    ParsedPeer(
                        comments=comments,
                        public_key=public_key,
                        allowed_ips=allowed_ips,
                        endpoint=endpoint,
                        persistent_keepalive=persistent_keepalive,
                        block_lines=block,
                    )
                )
        return interface_block, peers

    @staticmethod
    def _render_config(interface_block: list[str], peers: list[ParsedPeer]) -> str:
        lines = list(interface_block)
        while lines and lines[-1] == "":
            lines.pop()
        lines.append("")
        for index, peer in enumerate(peers):
            lines.extend(peer.block_lines)
            if index != len(peers) - 1:
                lines.append("")
        return "\n".join(lines).rstrip() + "\n"

    @staticmethod
    def _find_peer_by_public_key(peers: list[ParsedPeer], public_key: str) -> ParsedPeer | None:
        for peer in peers:
            if peer.public_key == public_key:
                return peer
        return None

    @staticmethod
    def _find_peer_for_session(peers: list[ParsedPeer], runtime_session_id: str, lease_type: str) -> ParsedPeer | None:
        wanted_session = f"# pivot.runtime_session_id={runtime_session_id}"
        wanted_type = f"# pivot.lease_type={lease_type}"
        for peer in peers:
            if wanted_session in peer.comments and wanted_type in peer.comments:
                return peer
        return None

    @staticmethod
    def _interface_network(interface_block: list[str]) -> ipaddress.IPv4Network:
        for line in interface_block:
            stripped = line.strip()
            if stripped.startswith("Address ="):
                first = stripped.split("=", 1)[1].split(",")[0].strip()
                return ipaddress.ip_interface(first).network
        raise AdapterHTTPException(500, "wireguard_interface_address_missing", "wireguard_config_invalid")

    @staticmethod
    def _existing_client_ips(peers: list[ParsedPeer], network: ipaddress.IPv4Network) -> set[ipaddress.IPv4Address]:
        used: set[ipaddress.IPv4Address] = set()
        for peer in peers:
            for allowed in peer.allowed_ips:
                try:
                    iface = ipaddress.ip_interface(allowed)
                except ValueError:
                    continue
                if iface.ip in network:
                    used.add(iface.ip)
        return used

    def _allocate_client_address(
        self,
        network: ipaddress.IPv4Network,
        used: set[ipaddress.IPv4Address],
    ) -> str:
        for host in range(self.settings.wireguard_client_ip_range_start, self.settings.wireguard_client_ip_range_end + 1):
            candidate = ipaddress.ip_address(int(network.network_address) + host)
            if candidate not in used and candidate != network.network_address and candidate != network.broadcast_address:
                return str(candidate)
        raise AdapterHTTPException(409, "wireguard_client_ip_pool_exhausted", "wireguard_conflict")

    def _interface_metadata(self, interface_block: list[str]) -> dict[str, object]:
        show_output = self.wireguard.show()
        public_key = None
        endpoint_port = None
        server_access_ip = None
        current_interface = None
        for line in show_output.splitlines():
            stripped = line.strip()
            if stripped.startswith("interface:"):
                current_interface = stripped.split(":", 1)[1].strip()
            elif current_interface == self.settings.wireguard_interface and stripped.startswith("public key:"):
                public_key = stripped.split(":", 1)[1].strip()
            elif current_interface == self.settings.wireguard_interface and stripped.startswith("listening port:"):
                endpoint_port = int(stripped.split(":", 1)[1].strip())
        for line in interface_block:
            stripped = line.strip()
            if stripped.startswith("Address ="):
                first = stripped.split("=", 1)[1].split(",")[0].strip()
                server_access_ip = str(ipaddress.ip_interface(first).ip)
                break
        return {
            "server_public_key": public_key,
            "server_access_ip": server_access_ip,
            "endpoint_host": self.settings.swarm_manager_addr,
            "endpoint_port": endpoint_port,
        }
