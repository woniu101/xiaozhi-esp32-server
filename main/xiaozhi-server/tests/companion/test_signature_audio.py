from __future__ import annotations

import base64
import hashlib
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from config.manage_api_client import ManageApiClient
from core.companion.signature_audio import (
    SignatureSpeechRouter,
    prefetch_signature_assets,
    render_signature_prompt,
)
from core.providers.tts.dto.dto import ContentType


def _session(asset_uri="asset://persona-signature/12345678abcdef"):
    signature = {
        "id": "ciallo",
        "display_text": "Ciallo～(∠・ω< )⌒★",
        "explicit_aliases": ["Ciallo"],
        "semantic_rule": "直接点名，或兔娘直播语境中的共享指代能唯一指向招牌问候时使用；间接点单可先装作没懂半拍",
        "assets": {"classic": asset_uri},
        "style_map": {"neutral": "classic"},
    }
    return SimpleNamespace(
        persona_spec=SimpleNamespace(signature_utterances=[signature]),
        signature_asset_files={asset_uri: "/tmp/ciallo.wav"},
        identity=SimpleNamespace(
            agent_id="agent-1",
            persona_id="persona.rabbit",
            persona_version="v1",
        ),
    )


class SignatureSpeechRouterTest(unittest.TestCase):
    def test_replaces_split_exact_phrase_with_file(self):
        router = SignatureSpeechRouter.from_session(
            _session(), {"primary_style": "neutral", "provider_hint": {"style": "neutral"}}
        )

        segments = router.feed("你好，Ci")
        segments += router.feed("allo～(∠・ω< )⌒★，今天也要开心。")
        segments += router.flush()

        files = [item for item in segments if item.content_type == ContentType.FILE]
        self.assertEqual(1, len(files))
        self.assertEqual("/tmp/ciallo.wav", files[0].file)
        self.assertEqual("Ciallo～(∠・ω< )⌒★", files[0].detail)
        self.assertEqual(
            "你好，，今天也要开心。",
            "".join(item.detail for item in segments if item.content_type == ContentType.TEXT),
        )

    def test_replaces_alias_only_on_final_flush(self):
        router = SignatureSpeechRouter.from_session(_session())
        self.assertEqual([], router.feed("Ciallo"))
        segments = router.flush()
        self.assertEqual(
            [(ContentType.FILE, "Ciallo～(∠・ω< )⌒★")],
            [(item.content_type, item.detail) for item in segments],
        )

    def test_completes_dangling_spoken_lead_in_before_recording(self):
        router = SignatureSpeechRouter.from_session(_session())

        segments = router.feed("哪个啊？你不说我怎么知——Ci")
        segments += router.feed("allo～(∠・ω< )⌒★")
        segments += router.flush()

        self.assertEqual(
            "哪个啊？你不说我怎么知道——",
            "".join(
                item.detail
                for item in segments
                if item.content_type == ContentType.TEXT
            ),
        )
        self.assertEqual(
            ["/tmp/ciallo.wav"],
            [
                item.file
                for item in segments
                if item.content_type == ContentType.FILE
            ],
        )

    def test_prompt_requires_a_complete_lead_in(self):
        prompt = render_signature_prompt(_session())
        self.assertIn("前导句必须是完整可朗读的短句", prompt)
        self.assertIn("你不说我怎么知道——", prompt)

    def test_without_registered_audio_is_passthrough(self):
        session = _session()
        session.signature_asset_files = {}
        router = SignatureSpeechRouter.from_session(session)
        segments = router.feed("Ciallo")
        self.assertEqual(
            [(ContentType.TEXT, "Ciallo")],
            [(item.content_type, item.detail) for item in segments],
        )


class SignatureAssetPrefetchTest(unittest.IsolatedAsyncioTestCase):
    async def test_validates_hash_and_populates_cache(self):
        audio = b"RIFF" + b"\x00" * 32
        digest = hashlib.sha256(audio).hexdigest()

        class FakeClient:
            async def _execute_async_request(self, method, endpoint, **kwargs):
                self.method = method
                self.endpoint = endpoint
                return {
                    "assetId": "12345678abcdef",
                    "sha256": digest,
                    "contentType": "audio/wav",
                    "audioBase64": base64.b64encode(audio).decode(),
                }

        fake_client = FakeClient()
        session = _session()
        with tempfile.TemporaryDirectory() as temp, patch.object(
            ManageApiClient, "_instance", fake_client
        ):
            count = await prefetch_signature_assets(
                session,
                {"companion": {"signature_cache_dir": temp}},
            )
            cached = Path(next(iter(session.signature_asset_files.values())))
            self.assertEqual(Path(temp), cached.parent)
            self.assertEqual(audio, cached.read_bytes())

        self.assertEqual(1, count)
        self.assertEqual("POST", fake_client.method)
        self.assertTrue(fake_client.endpoint.endswith("signature-asset"))


if __name__ == "__main__":
    unittest.main()
