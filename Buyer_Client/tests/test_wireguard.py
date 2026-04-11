from __future__ import annotations

import sys
import unittest
from pathlib import Path, PureWindowsPath
from subprocess import CompletedProcess
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from buyer_client_app.wireguard import bring_down, bring_up


class WireGuardWindowsTests(unittest.TestCase):
    def test_windows_bring_up_converges_when_tunnel_already_running_and_service_is_live(self) -> None:
        with (
            patch("buyer_client_app.wireguard._is_windows", return_value=True),
            patch("buyer_client_app.wireguard._resolve_wireguard_binary", return_value=r"C:\Program Files\WireGuard\wireguard.exe"),
            patch(
                "buyer_client_app.wireguard.subprocess.run",
                side_effect=[
                    CompletedProcess(
                        args=[],
                        returncode=1,
                        stdout="",
                        stderr="Error: Tunnel already installed and running",
                    ),
                    CompletedProcess(
                        args=[],
                        returncode=0,
                        stdout="Running",
                        stderr="",
                    ),
                    CompletedProcess(
                        args=[],
                        returncode=0,
                        stdout="interface: pivot-win",
                        stderr="",
                    ),
                ],
            ) as run,
            patch("buyer_client_app.wireguard.time.sleep"),
        ):
            result = bring_up(PureWindowsPath(r"D:\AI\Pivot_Client\buyer_client\sessions\runtime-1\wireguard\pivot-win.conf"))

        self.assertEqual(result["status"], "up")
        self.assertEqual(result["interface_name"], "pivot-win")
        self.assertTrue(result["converged"])
        self.assertEqual(result["probe"]["service_status"], "Running")
        self.assertTrue(result["probe"]["wg_show_ok"])
        self.assertEqual(run.call_count, 3)
        self.assertIn("/installtunnelservice", run.call_args_list[0].args[0])

    def test_windows_bring_up_uses_installtunnelservice(self) -> None:
        with (
            patch("buyer_client_app.wireguard._is_windows", return_value=True),
            patch("buyer_client_app.wireguard._resolve_wireguard_binary", return_value=r"C:\Program Files\WireGuard\wireguard.exe"),
            patch(
                "buyer_client_app.wireguard.subprocess.run",
                side_effect=[
                    CompletedProcess(
                        args=[],
                        returncode=0,
                        stdout="installed",
                        stderr="",
                    ),
                    CompletedProcess(
                        args=[],
                        returncode=0,
                        stdout="Running",
                        stderr="",
                    ),
                    CompletedProcess(
                        args=[],
                        returncode=0,
                        stdout="interface: pivot-win",
                        stderr="",
                    ),
                ],
            ) as run,
            patch("buyer_client_app.wireguard.time.sleep"),
        ):
            result = bring_up(PureWindowsPath(r"D:\AI\Pivot_Client\buyer_client\sessions\runtime-1\wireguard\pivot-win.conf"))

        self.assertEqual(result["status"], "up")
        self.assertEqual(result["interface_name"], "pivot-win")
        self.assertTrue(result["converged"])
        self.assertEqual(result["probe"]["service_status"], "Running")
        self.assertTrue(result["probe"]["wg_show_ok"])
        self.assertEqual(run.call_count, 3)
        self.assertIn("/installtunnelservice", run.call_args_list[0].args[0])

    def test_windows_bring_up_fails_when_already_running_but_service_probe_is_not_running(self) -> None:
        with (
            patch("buyer_client_app.wireguard._is_windows", return_value=True),
            patch("buyer_client_app.wireguard._resolve_wireguard_binary", return_value=r"C:\Program Files\WireGuard\wireguard.exe"),
            patch(
                "buyer_client_app.wireguard.subprocess.run",
                side_effect=[
                    CompletedProcess(
                        args=[],
                        returncode=1,
                        stdout="",
                        stderr="Error: Tunnel already installed and running",
                    ),
                    CompletedProcess(
                        args=[],
                        returncode=0,
                        stdout="Stopped",
                        stderr="",
                    ),
                    CompletedProcess(
                        args=[],
                        returncode=1,
                        stdout="",
                        stderr="Unable to access interface",
                    ),
                    CompletedProcess(
                        args=[],
                        returncode=0,
                        stdout="Stopped",
                        stderr="",
                    ),
                    CompletedProcess(
                        args=[],
                        returncode=1,
                        stdout="",
                        stderr="Unable to access interface",
                    ),
                    CompletedProcess(
                        args=[],
                        returncode=0,
                        stdout="Stopped",
                        stderr="",
                    ),
                    CompletedProcess(
                        args=[],
                        returncode=1,
                        stdout="",
                        stderr="Unable to access interface",
                    ),
                ],
            ),
            patch("buyer_client_app.wireguard.time.sleep"),
        ):
            with self.assertRaises(Exception):
                bring_up(PureWindowsPath(r"D:\AI\Pivot_Client\buyer_client\sessions\runtime-1\wireguard\pivot-win.conf"))

    def test_windows_bring_down_uses_uninstalltunnelservice(self) -> None:
        with (
            patch("buyer_client_app.wireguard._is_windows", return_value=True),
            patch("buyer_client_app.wireguard._resolve_wireguard_binary", return_value=r"C:\Program Files\WireGuard\wireguard.exe"),
            patch(
                "buyer_client_app.wireguard.subprocess.run",
                return_value=CompletedProcess(
                    args=[],
                    returncode=0,
                    stdout="removed",
                    stderr="",
                ),
            ) as run,
        ):
            result = bring_down(PureWindowsPath(r"D:\AI\Pivot_Client\buyer_client\sessions\runtime-1\wireguard\pivot-win.conf"))

        self.assertEqual(result["status"], "down")
        self.assertEqual(result["interface_name"], "pivot-win")
        run.assert_called_once()
        self.assertIn("/uninstalltunnelservice", run.call_args.args[0])


if __name__ == "__main__":
    unittest.main()
