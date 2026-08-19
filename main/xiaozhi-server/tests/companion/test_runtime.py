import asyncio
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

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
