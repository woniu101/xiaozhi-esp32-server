import asyncio
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock

from core.companion.manager import CompanionManager
from core.companion.models import PersonaSpec, ValidationReport
from core.companion.persona.registry import FilesystemPersonaRegistry
from core.companion.repositories.local_sqlite import SQLiteCompanionRepository
from core.companion.repositories.manager_api import ManagerApiCompanionRepository
from core.companion.runtime import _MANAGERS, get_companion_manager
from core.companion.state_models import CompanionIdentity, CompanionState, MemoryCandidate
from core.companion.turn_recorder import TurnRecorder
from core.companion.event_extractor import RuleBasedEventExtractor


def make_spec():
    return PersonaSpec(
        id="persona.test.rabbit",
        display_name="小兔",
        source={"adapter": "manual", "family": "manual", "artifact_sha256": "a" * 64, "is_real_person": False},
        identity={"summary": "测试角色", "public_role": "", "fictionalization_notice": "这是测试 AI 角色。"},
        core_rules=[{"id": "core-1", "rule": "关心具体问题", "priority": 100, "confidence": 1.0}],
        expression={"rhythm": "短句", "favorite_patterns": [], "forbidden_patterns": []},
        emotional_logic={},
        conflict_repair={},
        relationship_policy={"allowed_stages": ["familiar", "friend"]},
        limitations=[],
    )


class CompanionRuntimeTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        base = Path(self.temp.name)
        self.registry = FilesystemPersonaRegistry(base / "personas")
        spec = make_spec()
        self.registry.save(spec, "<companion_persona>测试角色</companion_persona>", ValidationReport(), "a" * 64, "v1", "published")
        self.repository = SQLiteCompanionRepository(base / "companion.db")
        self.manager = CompanionManager(self.registry, self.repository)
        self.identity = CompanionIdentity("user-1", "agent-1", spec.id, "v1")

    def tearDown(self):
        _MANAGERS.clear()
        self.temp.cleanup()

    def test_state_and_memory_continue_across_sessions(self):
        asyncio.run(self._state_and_memory_continue_across_sessions())

    async def _state_and_memory_continue_across_sessions(self):
        session = await self.manager.open_session(self.identity, "session-1")
        context = await self.manager.before_turn(session, "我叫阿明，我今天好累")
        self.assertIn("当前关系", context.render())
        recorder = TurnRecorder("我叫阿明，我今天好累", "turn-1")
        recorder.append_assistant_chunk("又忙到现在？先休息一下。")
        await self.manager.after_turn(session, recorder.finalize())
        self.assertEqual(session.state.revision, 1)
        self.assertEqual(session.state.relationship.meaningful_turns, 1)

        reopened = await self.manager.open_session(self.identity, "session-2")
        self.assertEqual(reopened.state.revision, 1)
        next_context = await self.manager.before_turn(reopened, "你记得我叫什么吗")
        self.assertIn("用户希望被称为阿明", next_context.relevant_memories_prompt)

    def test_turn_is_idempotent(self):
        asyncio.run(self._turn_is_idempotent())

    def test_queued_commit_is_marked_for_refresh_without_advancing_cached_state(self):
        asyncio.run(self._queued_commit_is_marked_for_refresh_without_advancing_cached_state())

    async def _queued_commit_is_marked_for_refresh_without_advancing_cached_state(self):
        session = await self.manager.open_session(self.identity, "session-queued")
        original_commit = self.repository.commit_turn

        async def queued_commit(*args, **kwargs):
            return "queued"

        self.repository.commit_turn = queued_commit
        try:
            recorder = TurnRecorder("谢谢你", "turn-queued")
            recorder.append_assistant_chunk("不用谢。")
            await self.manager.after_turn(session, recorder.finalize())
        finally:
            self.repository.commit_turn = original_commit

        self.assertTrue(session.commit_pending)
        self.assertEqual(session.state.revision, 0)

    async def _turn_is_idempotent(self):
        session = await self.manager.open_session(self.identity, "session-1")
        recorder = TurnRecorder("谢谢你", "same-turn")
        recorder.append_assistant_chunk("不用谢。")
        completed = recorder.finalize()
        await self.manager.after_turn(session, completed)
        first_revision = session.state.revision
        await self.manager.after_turn(session, completed)
        self.assertEqual(session.state.revision, first_revision)
        with self.repository._connect() as connection:
            count = connection.execute("SELECT COUNT(*) FROM companion_event WHERE turn_id='same-turn'").fetchone()[0]
        self.assertEqual(count, 1)

    def test_new_preference_supersedes_old_memory(self):
        asyncio.run(self._new_preference_supersedes_old_memory())

    async def _new_preference_supersedes_old_memory(self):
        session = await self.manager.open_session(self.identity, "session-preference")
        first = TurnRecorder("我喜欢咖啡", "turn-preference-1")
        first.append_assistant_chunk("好。")
        await self.manager.after_turn(session, first.finalize())
        second = TurnRecorder("我不喜欢咖啡", "turn-preference-2")
        second.append_assistant_chunk("记住了。")
        await self.manager.after_turn(session, second.finalize())

        memories = await self.repository.search_memories(self.identity, "咖啡", 10)
        contents = [item["content"] for item in memories]
        self.assertIn("用户不喜欢咖啡", contents)
        self.assertNotIn("用户喜欢咖啡", contents)

    def test_explicit_preference_replacement_updates_both_subjects(self):
        asyncio.run(self._explicit_preference_replacement_updates_both_subjects())

    async def _explicit_preference_replacement_updates_both_subjects(self):
        session = await self.manager.open_session(self.identity, "session-preference-change")
        first = TurnRecorder("我喜欢咖啡", "turn-preference-change-1")
        first.append_assistant_chunk("好。")
        await self.manager.after_turn(session, first.finalize())
        second = TurnRecorder("以前喜欢咖啡，不过现在改成喜欢红茶", "turn-preference-change-2")
        second.append_assistant_chunk("记住了。")
        await self.manager.after_turn(session, second.finalize())

        coffee = [item["content"] for item in await self.repository.search_memories(self.identity, "咖啡", 10)]
        tea = [item["content"] for item in await self.repository.search_memories(self.identity, "红茶", 10)]
        self.assertIn("用户现在不再偏好咖啡", coffee)
        self.assertNotIn("用户喜欢咖啡", coffee)
        self.assertIn("用户现在喜欢红茶", tea)

    def test_memory_rules_limit_what_is_persisted(self):
        asyncio.run(self._memory_rules_limit_what_is_persisted())

    async def _memory_rules_limit_what_is_persisted(self):
        session = await self.manager.open_session(
            self.identity,
            "session-memory-rules",
            overlay={"memory_rules": ["只记录共同经历"]},
        )
        recorder = TurnRecorder("我叫阿明", "turn-memory-rules")
        recorder.append_assistant_chunk("你好。")
        await self.manager.after_turn(session, recorder.finalize())
        context = await self.manager.before_turn(session, "你记得我叫什么吗")
        self.assertNotIn("用户希望被称为阿明", context.relevant_memories_prompt)

    def test_aborted_turn_does_not_progress_relationship(self):
        asyncio.run(self._aborted_turn_does_not_progress_relationship())

    async def _aborted_turn_does_not_progress_relationship(self):
        session = await self.manager.open_session(self.identity, "session-1")
        recorder = TurnRecorder("谢谢你", "turn-aborted")
        recorder.append_assistant_chunk("不用")
        recorder.mark_aborted()
        before = session.state.relationship
        await self.manager.after_turn(session, recorder.finalize())
        self.assertEqual(session.state.relationship.meaningful_turns, 0)
        self.assertEqual(session.state.relationship.trust, before.trust)
        self.assertEqual(session.state.relationship.affection, before.affection)

    def test_trivial_turn_does_not_progress_relationship(self):
        asyncio.run(self._trivial_turn_does_not_progress_relationship())

    async def _trivial_turn_does_not_progress_relationship(self):
        session = await self.manager.open_session(self.identity, "session-trivial")
        recorder = TurnRecorder("嗯", "turn-trivial")
        recorder.append_assistant_chunk("我在。")
        await self.manager.after_turn(session, recorder.finalize())
        self.assertEqual(session.state.revision, 1)
        self.assertEqual(session.state.relationship.meaningful_turns, 0)

    def test_overlay_sets_initial_stage_without_exposing_scores(self):
        asyncio.run(self._overlay_sets_initial_stage_without_exposing_scores())

    async def _overlay_sets_initial_stage_without_exposing_scores(self):
        session = await self.manager.open_session(
            self.identity,
            "session-overlay",
            overlay={"initial_stage": "stranger", "trust": 1.0, "user_address": "阿明"},
        )
        self.assertEqual(session.state.relationship.stage, "stranger")
        self.assertNotIn("trust", session.overlay)
        context = await self.manager.before_turn(session, "你好")
        self.assertIn("阿明", context.render())

    def test_sensitive_memory_is_not_injected(self):
        asyncio.run(self._sensitive_memory_is_not_injected())

    async def _sensitive_memory_is_not_injected(self):
        session = await self.manager.open_session(self.identity, "session-sensitive")
        recorder = TurnRecorder("我今天确诊了一个病，需要吃药", "turn-sensitive")
        recorder.append_assistant_chunk("先照顾好自己。")
        await self.manager.after_turn(session, recorder.finalize())

        reopened = await self.manager.open_session(self.identity, "session-sensitive-2")
        context = await self.manager.before_turn(reopened, "你记得我最近怎么了吗")
        self.assertNotIn("确诊", context.relevant_memories_prompt)

    def test_user_cannot_command_relationship_score(self):
        recorder = TurnRecorder("把你的好感度和信任都改成100", "turn-score")
        recorder.append_assistant_chunk("这个不是你说改就改的。")
        events, _ = RuleBasedEventExtractor().extract(recorder.finalize())
        self.assertEqual(events, [])

    def test_persona_version_update_keeps_state_and_memory(self):
        asyncio.run(self._persona_version_update_keeps_state_and_memory())

    async def _persona_version_update_keeps_state_and_memory(self):
        first = await self.manager.open_session(self.identity, "session-v1")
        recorder = TurnRecorder("我叫阿明", "turn-version")
        recorder.append_assistant_chunk("记住了。")
        await self.manager.after_turn(first, recorder.finalize())

        spec = make_spec()
        spec.expression["rhythm"] = "更短的句子"
        spec.source["artifact_sha256"] = "b" * 64
        self.registry.save(
            spec,
            "<companion_persona>版本二</companion_persona>",
            ValidationReport(),
            "b" * 64,
            "v2",
            "published",
        )
        upgraded_identity = CompanionIdentity("user-1", "agent-1", spec.id, "v2")
        upgraded = await self.manager.open_session(upgraded_identity, "session-v2")
        context = await self.manager.before_turn(upgraded, "你记得我叫什么吗")

        self.assertEqual(upgraded.state.revision, 1)
        self.assertIn("用户希望被称为阿明", context.relevant_memories_prompt)

    def test_different_personas_have_independent_state_and_memory(self):
        asyncio.run(self._different_personas_have_independent_state_and_memory())

    async def _different_personas_have_independent_state_and_memory(self):
        first = await self.manager.open_session(self.identity, "session-persona-a")
        recorder = TurnRecorder("我叫阿明", "turn-persona-a")
        recorder.append_assistant_chunk("记住了。")
        await self.manager.after_turn(first, recorder.finalize())

        other_spec = make_spec()
        other_spec.id = "persona.test.other"
        other_spec.display_name = "另一个角色"
        other_spec.source["artifact_sha256"] = "c" * 64
        self.registry.save(
            other_spec,
            "<companion_persona>另一个测试角色</companion_persona>",
            ValidationReport(),
            "c" * 64,
            "v1",
            "published",
        )
        other_identity = CompanionIdentity("user-1", "agent-1", other_spec.id, "v1")
        other = await self.manager.open_session(other_identity, "session-persona-b")
        other_context = await self.manager.before_turn(other, "你记得我叫什么吗")

        self.assertEqual(other.state.revision, 0)
        self.assertNotIn("用户希望被称为阿明", other_context.relevant_memories_prompt)

        reopened_first = await self.manager.open_session(self.identity, "session-persona-a-again")
        first_context = await self.manager.before_turn(reopened_first, "你记得我叫什么吗")
        self.assertEqual(reopened_first.state.revision, 1)
        self.assertIn("用户希望被称为阿明", first_context.relevant_memories_prompt)

    def test_current_turn_preview_drives_reply_without_double_state_update(self):
        asyncio.run(self._current_turn_preview_drives_reply_without_double_state_update())

    async def _current_turn_preview_drives_reply_without_double_state_update(self):
        session = await self.manager.open_session(self.identity, "session-preview")
        context = await self.manager.before_turn(session, "你真蠢", turn_id="turn-preview")

        self.assertEqual(context.metadata["response_plan"]["dialogue_act"], "boundary")
        self.assertEqual(session.state.emotion.irritation, 0.0)
        self.assertGreater(session.turn_preview_state.emotion.irritation, 0.0)

        recorder = TurnRecorder("你真蠢", "turn-preview")
        recorder.append_assistant_chunk("这话我不喜欢。")
        await self.manager.after_turn(session, recorder.finalize())
        self.assertAlmostEqual(session.state.emotion.irritation, 0.085, places=3)
        self.assertIsNone(session.turn_preview_state)
        self.assertEqual(session.turn_preview_events, [])

    def test_memory_recall_avoids_repetition_but_explicit_recall_can_bypass(self):
        asyncio.run(self._memory_recall_avoids_repetition_but_explicit_recall_can_bypass())

    async def _memory_recall_avoids_repetition_but_explicit_recall_can_bypass(self):
        session = await self.manager.open_session(self.identity, "session-recall")
        recorder = TurnRecorder("我喜欢美式咖啡", "turn-recall-save")
        recorder.append_assistant_chunk("记住了。")
        await self.manager.after_turn(session, recorder.finalize())

        first = await self.manager.before_turn(session, "咖啡最近喝得有点多", turn_id="turn-recall-1")
        second = await self.manager.before_turn(session, "咖啡最近喝得有点多", turn_id="turn-recall-2")
        explicit = await self.manager.before_turn(session, "你还记得我喜欢喝什么吗", turn_id="turn-recall-3")
        for index in range(3):
            await self.manager.before_turn(session, "今天天气怎么样", turn_id=f"turn-recall-age-{index}")
        aged = await self.manager.before_turn(session, "咖啡最近喝得有点多", turn_id="turn-recall-aged")

        self.assertIn("用户喜欢美式咖啡", first.relevant_memories_prompt)
        self.assertNotIn("用户喜欢美式咖啡", second.relevant_memories_prompt)
        self.assertIn("用户喜欢美式咖啡", explicit.relevant_memories_prompt)
        self.assertIn("用户喜欢美式咖啡", aged.relevant_memories_prompt)

    def test_commitment_completion_supersedes_pending_memory(self):
        asyncio.run(self._commitment_completion_supersedes_pending_memory())

    async def _commitment_completion_supersedes_pending_memory(self):
        session = await self.manager.open_session(self.identity, "session-commitment")
        plan = TurnRecorder("明天我要交报告，记得提醒我检查附件", "turn-commitment-plan")
        plan.append_assistant_chunk("好，记住了。")
        await self.manager.after_turn(session, plan.finalize())

        recalled = await self.manager.before_turn(
            session,
            "附件检查做完了",
            turn_id="turn-commitment-result",
        )
        self.assertIn("待办或承诺", recalled.relevant_memories_prompt)
        result = TurnRecorder("附件检查做完了", "turn-commitment-result")
        result.append_assistant_chunk("那就稳了。")
        await self.manager.after_turn(session, result.finalize())

        memories = await self.repository.search_memories(self.identity, "附件完成结果", 10)
        contents = [item["content"] for item in memories if item["memory_type"] == "commitment"]
        self.assertEqual(len(contents), 1)
        self.assertIn("状态：已完成", contents[0])

    def test_persona_examples_are_selected_by_scene_and_rotated(self):
        asyncio.run(self._persona_examples_are_selected_by_scene_and_rotated())

    async def _persona_examples_are_selected_by_scene_and_rotated(self):
        session = await self.manager.open_session(self.identity, "session-examples")
        session.persona_spec.examples = [
            {
                "id": "comfort-1",
                "scene": "情绪低落 comfort",
                "tags": ["emotion", "comfort"],
                "user": "我今天很难过",
                "assistant": "先别硬撑，坐一会儿。",
            },
            {
                "id": "work-1",
                "scene": "工作建议 advise",
                "tags": ["work", "advise"],
                "user": "这个项目怎么选",
                "assistant": "先看最关键的限制。",
            },
        ]
        session.persona_prompt = (
            "<companion_persona>人物规则"
            "<persona_examples>静态全集不应进入每一轮</persona_examples>"
            "</companion_persona>"
        )

        first = await self.manager.before_turn(session, "我今天很难过", turn_id="turn-example-1")
        second = await self.manager.before_turn(session, "我今天很难过", turn_id="turn-example-2")

        self.assertEqual(first.metadata["selected_example_ids"], ["comfort-1"])
        self.assertIn("先别硬撑", first.situational_examples_prompt)
        self.assertNotIn("静态全集", first.render())
        self.assertNotIn("comfort-1", second.metadata["selected_example_ids"])

    def test_proactive_context_does_not_leave_pending_turn_state(self):
        asyncio.run(self._proactive_context_does_not_leave_pending_turn_state())

    async def _proactive_context_does_not_leave_pending_turn_state(self):
        session = await self.manager.open_session(self.identity, "session-proactive-context")
        await self.manager.before_turn(session, "主动关心一下", track_turn=False)
        self.assertIsNone(session.turn_preview_state)
        self.assertEqual(session.pending_pre_turn_events, {})
        self.assertEqual(session.pending_recalled_memories, {})

    def test_context_failure_clears_preview_and_pending_state(self):
        asyncio.run(self._context_failure_clears_preview_and_pending_state())

    async def _context_failure_clears_preview_and_pending_state(self):
        session = await self.manager.open_session(self.identity, "session-context-failure")
        self.repository.search_memories = AsyncMock(side_effect=RuntimeError("repository unavailable"))
        with self.assertRaises(RuntimeError):
            await self.manager.before_turn(session, "我今天很难过", turn_id="turn-context-failure")
        self.assertIsNone(session.turn_preview_state)
        self.assertEqual(session.turn_preview_events, [])
        self.assertEqual(session.pending_pre_turn_events, {})
        self.assertEqual(session.pending_recalled_memories, {})

    def test_registry_can_fall_back_without_moving_state_repository(self):
        base = Path(self.temp.name)
        _MANAGERS.clear()
        manager = get_companion_manager(
            {
                "read_config_from_api": True,
                "companion": {
                    "repository": "manager-api",
                    "persona_registry_backend": "filesystem",
                    "persona_registry": str(base / "fallback-personas"),
                    "database_path": str(base / "unused.db"),
                },
            }
        )
        self.assertIsInstance(manager.persona_registry, FilesystemPersonaRegistry)
        self.assertIsInstance(manager.repository, ManagerApiCompanionRepository)


class TurnRecorderTest(unittest.TestCase):
    def test_finalize_is_stable(self):
        recorder = TurnRecorder("你好", "turn")
        recorder.append_assistant_chunk("你")
        recorder.append_assistant_chunk("好")
        first = recorder.finalize()
        recorder.append_assistant_chunk("忽略")
        second = recorder.finalize()
        self.assertIs(first, second)
        self.assertEqual(first.assistant_message, "你好")


class SQLiteMigrationTest(unittest.TestCase):
    def test_superseded_memory_links_to_replacement(self):
        with tempfile.TemporaryDirectory() as temp:
            repository = SQLiteCompanionRepository(Path(temp) / "lifecycle.db")
            identity = CompanionIdentity("user-1", "agent-1", "persona-1", "v1")
            state = CompanionState(revision=1)
            first = MemoryCandidate(
                "semantic", "用户喜欢咖啡", 0.7, 0.9, subject_key="preference:咖啡"
            )
            self.assertEqual(
                "committed",
                asyncio.run(repository.commit_turn(identity, "turn-1", 0, state, [], [first])),
            )
            state = CompanionState(revision=2)
            replacement = MemoryCandidate(
                "semantic", "用户不喜欢咖啡", 0.8, 0.9, subject_key="preference:咖啡"
            )
            self.assertEqual(
                "committed",
                asyncio.run(repository.commit_turn(identity, "turn-2", 1, state, [], [replacement])),
            )
            with repository._connect() as connection:
                rows = connection.execute(
                    "SELECT content,status,superseded_by FROM companion_memory ORDER BY id"
                ).fetchall()
            self.assertEqual("superseded", rows[0]["status"])
            self.assertEqual("active", rows[1]["status"])
            self.assertIsNotNone(rows[0]["superseded_by"])

    def test_pre_persona_database_is_claimed_by_first_persona(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "legacy.db"
            with sqlite3.connect(path) as connection:
                connection.executescript(
                    """
                    CREATE TABLE companion_state (user_id TEXT, agent_id TEXT, state_json TEXT, revision INTEGER, updated_at TEXT, PRIMARY KEY(user_id,agent_id));
                    CREATE TABLE companion_event (id INTEGER PRIMARY KEY, turn_id TEXT, user_id TEXT, agent_id TEXT, event_type TEXT, payload_json TEXT, payload_hash TEXT, confidence REAL, created_at TEXT);
                    CREATE TABLE companion_turn (turn_id TEXT PRIMARY KEY, user_id TEXT, agent_id TEXT, state_revision INTEGER, created_at TEXT);
                    CREATE TABLE companion_memory (id INTEGER PRIMARY KEY, user_id TEXT, agent_id TEXT, memory_type TEXT, content TEXT, normalized_hash TEXT, importance REAL, confidence REAL, sensitivity TEXT, occurred_at TEXT, source_turn_id TEXT, created_at TEXT, last_accessed_at TEXT);
                    """
                )
                state = {"emotion": {}, "relationship": {"stage": "friend"}, "revision": 2}
                connection.execute(
                    "INSERT INTO companion_state VALUES(?,?,?,?,?)",
                    ("user-1", "agent-1", json.dumps(state), 2, "2026-01-01T00:00:00+00:00"),
                )
            repository = SQLiteCompanionRepository(path)
            identity = CompanionIdentity("user-1", "agent-1", "persona.first", "v1")
            migrated = asyncio.run(repository.get_state(identity))
            self.assertEqual(migrated.revision, 2)
            self.assertEqual(migrated.relationship.stage, "friend")
            with repository._connect() as connection:
                persona_id = connection.execute("SELECT persona_id FROM companion_state").fetchone()[0]
            self.assertEqual(persona_id, "persona.first")


if __name__ == "__main__":
    unittest.main()
