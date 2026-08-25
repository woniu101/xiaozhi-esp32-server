import tempfile
import unittest
import zipfile
from pathlib import Path

from core.companion.importers.compiler import PersonaCompiler
from core.companion.importers.dot_skill import DotSkillAdapter


SKILL = """---
name: 兔娘.skill
description: 兔娘对话人物
version: v1
---
# 兔娘

## 角色扮演规则
始终以兔娘第一人称思考和回应。

## 身份卡
你是兔娘，说话自然，不自称 AI。

## 表达DNA
短句、自然、有一点俏皮，但不机械重复口头禅。

## 对话纪律
- 招牌点单单独路由：用户直接点名 `Ciallo`，或在兔娘直播语境里说“想听那个了”“今天那个还没来”等共享指代，且上下文能唯一指向招牌问候时，可以先装作没懂半拍，再回 `Ciallo～(∠・ω< )⌒★`。说完即停，不解释出处；上下文不能唯一指向时，不强行猜成 `Ciallo`。
- 不要机械复读招牌语。

## 示例
**用户**：兔娘，想听那个了。
**我**：哪个啊？你不说我怎么知——Ciallo～(∠・ω< )⌒★
"""


class DotSkillLosslessTest(unittest.TestCase):
    def test_adapter_preserves_source_and_compiles_signature_rule(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "rabbit-skill"
            source.mkdir()
            (source / "SKILL.md").write_text(SKILL, encoding="utf-8")
            spec = DotSkillAdapter().convert(source).spec
        prompt = PersonaCompiler().compile(spec)

        self.assertEqual("兔娘", spec.display_name)
        self.assertEqual(SKILL.split("---", 2)[-1].strip(), spec.source_behavior.strip())
        self.assertEqual("lossless-hybrid", spec.conversion_coverage["mode"])
        self.assertEqual("ciallo", spec.signature_utterances[0]["id"])
        self.assertEqual("Ciallo～(∠・ω< )⌒★", spec.signature_utterances[0]["display_text"])
        self.assertEqual(
            "哪个啊？你不说我怎么知——Ciallo～(∠・ω< )⌒★",
            spec.examples[0]["assistant"],
        )
        self.assertIn("<upstream_persona_rules>", prompt)
        self.assertIn("上下文不能唯一指向时，不强行猜成", prompt)

    def test_inspect_and_convert_use_the_same_normalized_source_hash(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "rabbit-skill.zip"
            with zipfile.ZipFile(source, "w") as archive:
                archive.comment = b"archive metadata must not define source identity"
                archive.writestr("rabbit/SKILL.md", SKILL)
            adapter = DotSkillAdapter()
            inspection = adapter.inspect(source)
            converted = adapter.convert(source)

        self.assertEqual(converted.artifact_sha256, inspection.artifact_sha256)

    def test_ordinary_dialogue_example_does_not_make_signature_mandatory(self):
        ordinary_skill = SKILL.replace("招牌", "普通")
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "ordinary-persona"
            source.mkdir()
            (source / "SKILL.md").write_text(ordinary_skill, encoding="utf-8")
            spec = DotSkillAdapter().convert(source).spec

        self.assertEqual([], spec.signature_utterances)
        self.assertIn("Ciallo", spec.examples[0]["assistant"])

    def test_imports_linked_dialogue_and_fidelity_references(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "rabbit-skill"
            references = source / "references"
            references.mkdir(parents=True)
            (source / "SKILL.md").write_text(
                SKILL
                + "\n更多口吻样本见 [对话手册](references/dialogue-playbook.md)。\n",
                encoding="utf-8",
            )
            (references / "dialogue-playbook.md").write_text(
                "# 对话手册\n\n## 降温接梗\n"
                "**用户**：我火气有点大，能帮我降降温吗？<br>\n"
                "**我**：能啊，空调十六度。你先往后站一点。\n",
                encoding="utf-8",
            )
            (source / "FIDELITY.md").write_text(
                "# 保真回归\n\n新对话直接递出火气大、帮我降温时，"
                "可以当轮建立共玩，不要退回饮水建议。\n",
                encoding="utf-8",
            )

            converted = DotSkillAdapter().convert(source)
            spec = converted.spec

        self.assertIn("对话手册", spec.source_behavior)
        self.assertIn("保真回归", spec.source_behavior)
        self.assertIn(
            "能啊，空调十六度。你先往后站一点。",
            [item["assistant"] for item in spec.examples],
        )
        self.assertEqual(2, len(spec.conversion_coverage["behavior_reference_files"]))
        self.assertEqual(3, len(converted.source_files))
        self.assertIn("behavior_reference_sha256", spec.source)


if __name__ == "__main__":
    unittest.main()
