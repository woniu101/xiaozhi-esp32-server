import unittest
from pathlib import Path

from core.character_style.prompt import resolve_runtime_prompt


class CharacterStylePromptTest(unittest.TestCase):
    def test_unbound_agent_keeps_original_role_prompt(self):
        self.assertEqual(resolve_runtime_prompt("原角色介绍", None), "原角色介绍")
        self.assertEqual(
            resolve_runtime_prompt("原角色介绍", {"active": False}),
            "原角色介绍",
        )

    def test_bound_agent_uses_only_resolved_dot_skill_prompt(self):
        value = resolve_runtime_prompt(
            "原角色介绍不能进入运行时",
            {"active": True, "resolved_prompt": "<character_style>兔娘原文</character_style>"},
        )
        self.assertEqual(value, "<character_style>兔娘原文</character_style>")
        self.assertNotIn("原角色介绍", value)

    def test_bound_agent_without_resolved_prompt_fails_explicitly(self):
        with self.assertRaises(ValueError):
            resolve_runtime_prompt("原角色介绍", {"active": True})

    def test_enabled_recording_adds_only_a_surface_form_contract(self):
        prompt = resolve_runtime_prompt(
            "原角色介绍",
            {
                "active": True,
                "resolved_prompt": "兔娘原始 Skill",
                "signature_config": {
                    "enabled": True,
                    "items": [
                        {
                            "id": "ciallo",
                            "display_text": "Ciallo～(∠・ω< )⌒★",
                            "audio_path": "signatures/ciallo.wav",
                            "enabled": True,
                        },
                        {
                            "id": "disabled",
                            "display_text": "不要出现",
                            "audio_path": "signatures/disabled.wav",
                            "enabled": False,
                        },
                    ],
                },
            },
        )

        self.assertTrue(prompt.startswith("兔娘原始 Skill"))
        self.assertIn("<signature_audio_contract>", prompt)
        self.assertIn('"Ciallo～(∠・ω< )⌒★"', prompt)
        self.assertIn("不得提高使用频率", prompt)
        self.assertNotIn("不要出现", prompt)

    def test_disabled_recording_does_not_change_the_imported_prompt(self):
        self.assertEqual(
            "兔娘原始 Skill",
            resolve_runtime_prompt(
                "原角色介绍",
                {
                    "active": True,
                    "resolved_prompt": "兔娘原始 Skill",
                    "signature_config": {"enabled": False, "items": []},
                },
            ),
        )

    def test_character_template_is_neutral_and_keeps_runtime_contracts(self):
        template = (
            Path(__file__).resolve().parents[1] / "agent-character-style-prompt.txt"
        ).read_text(encoding="utf-8")
        lower = template.lower()
        self.assertNotIn("playful", lower)
        self.assertNotIn("warm", lower)
        self.assertNotIn("poetic", lower)
        self.assertIn("tolerate asr errors", lower)
        self.assertIn("tool_and_knowledge", lower)
        self.assertIn("tts_format_constraints", lower)
        self.assertIn("{{base_prompt}}", template)


if __name__ == "__main__":
    unittest.main()
