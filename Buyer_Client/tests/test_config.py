from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from buyer_client_app.config import Settings


class SettingsTests(unittest.TestCase):
    def test_from_env_uses_typed_instance_defaults(self) -> None:
        env_keys = (
            "BUYER_CLIENT_APP_HOST",
            "BUYER_CLIENT_APP_PORT",
            "BUYER_CLIENT_BACKEND_BASE_URL",
            "BUYER_CLIENT_BACKEND_API_PREFIX",
            "BUYER_CLIENT_WINDOWS_WORKSPACE_ROOT",
            "BUYER_CLIENT_NON_WINDOWS_WORKSPACE_ROOT",
            "BUYER_CLIENT_SESSION_SUBDIR_NAME",
            "BUYER_CLIENT_LOGS_SUBDIR_NAME",
            "BUYER_CLIENT_WORKSPACE_SUBDIR_NAME",
            "BUYER_CLIENT_WINDOW_SESSION_TTL_SECONDS",
            "BUYER_CLIENT_HEARTBEAT_INTERVAL_SECONDS",
            "BUYER_CLIENT_DEFAULT_REQUESTED_DURATION_MINUTES",
        )
        with patch.dict(os.environ, {}, clear=False):
            for key in env_keys:
                os.environ.pop(key, None)
            settings = Settings.from_env()

        self.assertIsInstance(settings.app_host, str)
        self.assertIsInstance(settings.app_port, int)
        self.assertEqual(settings.window_session_ttl_seconds, 90)
        self.assertEqual(settings.heartbeat_interval_seconds, 30)
        self.assertEqual(settings.default_requested_duration_minutes, 60)


if __name__ == "__main__":
    unittest.main()
