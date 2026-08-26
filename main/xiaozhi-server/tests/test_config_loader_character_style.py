import asyncio
import os
import unittest
from unittest.mock import AsyncMock, patch

from config.config_loader import get_config_from_api_async


class CharacterStyleConfigLoaderTest(unittest.TestCase):
    def base_config(self):
        return {
            "manager-api": {"url": "http://manager", "secret": "secret"},
            "server": {"ip": "0.0.0.0", "port": 8000, "http_port": 8003},
        }

    def fetch(self, local_config):
        server_config = {
            "server": {"auth": {"enabled": False}},
            "selected_module": {},
        }
        with patch("config.config_loader.init_service"), patch(
            "config.config_loader.get_server_config",
            new=AsyncMock(return_value=server_config),
        ):
            return asyncio.run(get_config_from_api_async(local_config))

    def test_local_shared_data_dir_survives_manager_api_config_replacement(self):
        local = self.base_config()
        local["character_style_data_dir"] = "/opt/xiaozhi-esp32-server/data"

        result = self.fetch(local)

        self.assertEqual(
            "/opt/xiaozhi-esp32-server/data",
            result["character_style_data_dir"],
        )

    def test_shared_character_style_environment_variable_is_also_supported(self):
        with patch.dict(
            os.environ,
            {"CHARACTER_STYLE_DIR": "/shared/data/character_styles"},
        ):
            result = self.fetch(self.base_config())

        self.assertEqual("/shared/data", result["character_style_data_dir"])


if __name__ == "__main__":
    unittest.main()
