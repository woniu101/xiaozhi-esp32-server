import tempfile
import unittest
import wave
from pathlib import Path

from core.character_style.models import SignatureSegmentType
from core.character_style.signature_asset import character_style_data_dir
from core.character_style.signature_router import create_signature_router


DISPLAY = "Ciallo~(∠・ω< )⌒★"


class SignatureRouterTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.storage = Path(self.temp.name)
        self.audio = self.storage / "character_styles" / "rabbit" / "signatures" / "ciallo.wav"
        self.audio.parent.mkdir(parents=True)
        write_wav(self.audio)

    def tearDown(self):
        self.temp.cleanup()

    def style(self, *, global_enabled=True, item_enabled=True, audio_path="signatures/ciallo.wav"):
        return {
            "active": True,
            "asset_root": "character_styles/rabbit",
            "signature_config": {
                "enabled": global_enabled,
                "items": [
                    {
                        "id": "ciallo",
                        "display_text": DISPLAY,
                        "aliases": ["Ciallo"],
                        "audio_path": audio_path,
                        "enabled": item_enabled,
                    }
                ],
            },
        }

    def test_cross_chunk_longest_display_is_consumed_as_one_file(self):
        router = create_signature_router(self.style(), self.storage)

        segments = []
        for chunk in ["你不说我怎么知道——Cia", "llo~(∠・ω< )", "⌒★ 今天聊什么？"]:
            segments.extend(router.feed(chunk))
        segments.extend(router.flush())
        logical_segments = coalesce_text(segments)

        self.assertEqual(
            [SignatureSegmentType.TEXT, SignatureSegmentType.FILE, SignatureSegmentType.TEXT],
            [segment.segment_type for segment in logical_segments],
        )
        self.assertEqual(DISPLAY, logical_segments[1].text)
        self.assertEqual(str(self.audio.resolve()), logical_segments[1].audio_file)
        self.assertEqual(
            "你不说我怎么知道——" + DISPLAY + " 今天聊什么？",
            "".join(segment.text for segment in segments),
        )

    def test_explicit_shared_data_dir_overrides_log_directory(self):
        selected = character_style_data_dir(
            {
                "character_style_data_dir": "/opt/xiaozhi-esp32-server/data",
                "log": {"data_dir": "data"},
            },
            "/workspace/server",
        )

        self.assertEqual("/opt/xiaozhi-esp32-server/data", selected)

    def test_alias_is_case_insensitive_respects_boundary_and_plays_once(self):
        router = create_signature_router(self.style(), self.storage)

        segments = router.feed("sociallo CIALLO! Ciallo?") + router.flush()

        files = [value for value in segments if value.segment_type is SignatureSegmentType.FILE]
        self.assertEqual(1, len(files))
        self.assertEqual("CIALLO", files[0].text)
        self.assertEqual("sociallo CIALLO! Ciallo?", "".join(value.text for value in segments))
        self.assertEqual(frozenset({"ciallo"}), router.played_item_ids)

    def test_optional_switches_and_invalid_audio_fall_back_to_text(self):
        cases = [
            self.style(global_enabled=False),
            self.style(item_enabled=False),
            self.style(audio_path=None),
            self.style(audio_path="signatures/missing.wav"),
            {"active": False, "signature_config": {"enabled": True, "items": []}},
        ]
        for style in cases:
            with self.subTest(style=style):
                router = create_signature_router(style, self.storage)
                segments = router.feed(DISPLAY) + router.flush()
                self.assertEqual([SignatureSegmentType.TEXT], [value.segment_type for value in segments])
                self.assertEqual(DISPLAY, "".join(value.text for value in segments))

    def test_corrupt_and_traversal_audio_paths_are_rejected(self):
        corrupt = self.audio.parent / "corrupt.wav"
        corrupt.write_bytes(b"RIFF broken")
        truncated = self.audio.parent / "truncated.wav"
        truncated.write_bytes(self.audio.read_bytes()[:-100])
        for audio_path in [
            "signatures/corrupt.wav",
            "signatures/truncated.wav",
            "../outside.wav",
            "/tmp/outside.wav",
        ]:
            with self.subTest(audio_path=audio_path):
                router = create_signature_router(self.style(audio_path=audio_path), self.storage)
                segments = router.feed("Ciallo!") + router.flush()
                self.assertTrue(all(value.segment_type is SignatureSegmentType.TEXT for value in segments))

    def test_short_alias_waits_until_long_display_can_be_decided(self):
        router = create_signature_router(self.style(), self.storage)

        first = router.feed("Ciallo~")
        second = router.feed("(∠・ω< )⌒★")
        final = router.flush()

        self.assertEqual([], first)
        files = [value for value in second + final if value.segment_type is SignatureSegmentType.FILE]
        self.assertEqual([DISPLAY], [value.text for value in files])


def write_wav(path: Path):
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(24_000)
        wav.writeframes(b"\x00\x00" * 12_000)


def coalesce_text(segments):
    output = []
    for segment in segments:
        if output and output[-1].segment_type is SignatureSegmentType.TEXT \
                and segment.segment_type is SignatureSegmentType.TEXT:
            previous = output[-1]
            output[-1] = type(previous)(previous.segment_type, previous.text + segment.text)
        else:
            output.append(segment)
    return output


if __name__ == "__main__":
    unittest.main()
