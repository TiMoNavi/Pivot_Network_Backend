from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from seller_client_app.config import Settings


class SettingsTests(unittest.TestCase):
    def test_from_env_uses_typed_instance_defaults(self) -> None:
        env_keys = (
            "SELLER_CLIENT_APP_HOST",
            "SELLER_CLIENT_APP_PORT",
            "SELLER_CLIENT_BACKEND_BASE_URL",
            "SELLER_CLIENT_BACKEND_API_PREFIX",
            "SELLER_CLIENT_WINDOWS_WORKSPACE_ROOT",
            "SELLER_CLIENT_NON_WINDOWS_WORKSPACE_ROOT",
            "SELLER_CLIENT_SESSION_SUBDIR_NAME",
            "SELLER_CLIENT_LOGS_SUBDIR_NAME",
            "SELLER_CLIENT_WORKSPACE_SUBDIR_NAME",
            "SELLER_CLIENT_CODEX_COMMAND",
            "SELLER_CLIENT_CODEX_MCP_SERVER_NAME_PREFIX",
            "SELLER_CLIENT_CODEX_EXEC_TIMEOUT_SECONDS",
            "SELLER_CLIENT_CODEX_EXEC_SANDBOX",
            "SELLER_CLIENT_CODEX_CONFIG_TEMPLATE_PATH",
            "SELLER_CLIENT_CODEX_AUTH_SOURCE_PATH",
            "SELLER_CLIENT_WINDOW_SESSION_TTL_SECONDS",
            "SELLER_CLIENT_WINDOW_SESSION_HEARTBEAT_INTERVAL_SECONDS",
            "SELLER_CLIENT_HEARTBEAT_INTERVAL_SECONDS",
            "SELLER_CLIENT_WINDOWS_DEPLOY_ROOT",
            "SELLER_CLIENT_WINDOWS_SSH_HOST_ALIAS",
        )
        with patch.dict(os.environ, {}, clear=False):
            for key in env_keys:
                os.environ.pop(key, None)
            settings = Settings.from_env()

        self.assertIsInstance(settings.app_host, str)
        self.assertIsInstance(settings.app_port, int)
        self.assertIsInstance(settings.window_session_ttl_seconds, int)
        self.assertEqual(settings.window_session_ttl_seconds, 90)
        self.assertEqual(settings.window_session_heartbeat_interval_seconds, 15)
        self.assertEqual(settings.heartbeat_interval_seconds, 30)


if __name__ == "__main__":
    unittest.main()
