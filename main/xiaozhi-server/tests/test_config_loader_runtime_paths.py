import asyncio
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from config.config_loader import apply_runtime_output_dirs, get_private_config_from_api


class RuntimePathConfigTest(unittest.TestCase):
    def test_output_directories_move_to_data_disk(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            os.environ, {"XIAOZHI_OUTPUT_DIR": directory}
        ):
            config = {
                "ASR": {"Fun ASR": {"output_dir": "tmp/", "model_dir": "models/asr"}},
                "TTS": {"IndexTTS2_5": {"output_dir": "tmp/", "api_url": "http://tts"}},
            }

            result = apply_runtime_output_dirs(config)

            self.assertEqual(
                str(Path(directory).resolve() / "asr" / "Fun-ASR"),
                result["ASR"]["Fun ASR"]["output_dir"],
            )
            self.assertEqual(
                str(Path(directory).resolve() / "tts" / "IndexTTS2_5"),
                result["TTS"]["IndexTTS2_5"]["output_dir"],
            )
            self.assertEqual("models/asr", result["ASR"]["Fun ASR"]["model_dir"])

    def test_no_environment_override_keeps_existing_paths(self):
        with patch.dict(os.environ, {}, clear=True):
            config = {"TTS": {"edge": {"output_dir": "tmp/"}}}
            self.assertEqual("tmp/", apply_runtime_output_dirs(config)["TTS"]["edge"]["output_dir"])

    def test_private_agent_models_are_rewritten_before_use(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            os.environ, {"XIAOZHI_OUTPUT_DIR": directory}
        ), patch(
            "config.config_loader.get_agent_models",
            new=AsyncMock(
                return_value={
                    "TTS": {"TTS_IndexTTS2_5": {"output_dir": "tmp/"}},
                    "selected_module": {"TTS": "TTS_IndexTTS2_5"},
                }
            ),
        ), patch(
            "config.config_loader.get_correct_words", new=AsyncMock(return_value=None)
        ):
            result = asyncio.run(
                get_private_config_from_api({"selected_module": {}}, "device", "client")
            )

            expected = Path(directory).resolve() / "tts" / "TTS_IndexTTS2_5"
            self.assertEqual(
                str(expected), result["TTS"]["TTS_IndexTTS2_5"]["output_dir"]
            )
            self.assertTrue(expected.is_dir())


if __name__ == "__main__":
    unittest.main()
