import asyncio
import unittest

from core.companion.repositories.manager_api import ManagerApiCompanionRepository
from core.companion.persona.manager_api_registry import ManagerApiPersonaRegistry
from core.companion.state_models import CompanionEvent, CompanionIdentity, CompanionState, MemoryCandidate


class FakeManagerClient:
    def __init__(self):
        self.calls = []

    async def _execute_async_request(self, method, endpoint, **kwargs):
        self.calls.append((method, endpoint, kwargs.get("json")))
        if endpoint.endswith("/state"):
            return {"emotion": {"warmth": 0.8}, "relationship": {}, "revision": 3}
        if endpoint.endswith("/commit"):
            return "committed"
        if endpoint.endswith("/persona/resolve"):
            return {
                "notModified": False,
                "personaId": "persona.test.rabbit",
                "version": "v1",
                "artifactHash": "a" * 64,
                "compilerVersion": "test/1",
                "canonicalSpec": {
                    "schema_version": "cyber-persona/v1",
                    "id": "persona.test.rabbit",
                    "display_name": "小兔",
                    "source": {"adapter": "manual", "family": "manual", "artifact_sha256": "a" * 64},
                    "identity": {"summary": "测试"},
                },
                "runtimePrompt": "<companion_persona>测试</companion_persona>",
            }
        return [
            {"id": 1, "memoryType": "semantic", "content": "用户希望被称为阿明", "importance": 0.7, "confidence": 0.9, "sensitivity": "personal"},
            {"id": 2, "memoryType": "episodic", "content": "用户的诊断信息", "importance": 1.0, "confidence": 1.0, "sensitivity": "sensitive"},
        ]


class TestRepository(ManagerApiCompanionRepository):
    def __init__(self, client):
        self.client = client

    def _client(self):
        return self.client


class ManagerRepositoryTest(unittest.TestCase):
    def test_state_commit_and_memory_contract(self):
        asyncio.run(self._state_commit_and_memory_contract())

    async def _state_commit_and_memory_contract(self):
        client = FakeManagerClient()
        repository = TestRepository(client)
        identity = CompanionIdentity("user-1", "agent-1", "persona-1")

        state = await repository.get_state(identity)
        self.assertEqual(state.revision, 3)
        self.assertEqual(state.emotion.warmth, 0.8)

        next_state = CompanionState.from_dict(state.to_dict())
        next_state.revision = 4
        result = await repository.commit_turn(
            identity,
            "turn-1",
            3,
            next_state,
            [CompanionEvent("user_showed_care", 0.8)],
            [MemoryCandidate("semantic", "用户喜欢咖啡", 0.7, 0.8)],
        )
        self.assertEqual(result, "committed")
        commit_payload = next(call[2] for call in client.calls if call[1].endswith("/commit"))
        self.assertEqual(commit_payload["expectedRevision"], 3)
        self.assertEqual(commit_payload["personaId"], "persona-1")
        self.assertEqual(commit_payload["events"][0]["eventType"], "user_showed_care")

        memories = await repository.search_memories(identity, "你记得我叫什么吗", 6)
        self.assertEqual([item["content"] for item in memories], ["用户希望被称为阿明"])

    def test_persona_registry_resolves_and_caches(self):
        asyncio.run(self._persona_registry_resolves_and_caches())

    async def _persona_registry_resolves_and_caches(self):
        client = FakeManagerClient()
        registry = ManagerApiPersonaRegistry(client=client)
        first = await registry.load_for_runtime("persona.test.rabbit", None, agent_id="agent-1")
        second = await registry.load_for_runtime("persona.test.rabbit", None, agent_id="agent-1")
        self.assertEqual(first[0].display_name, "小兔")
        self.assertEqual(first[2]["version"], "v1")
        self.assertEqual(second[1], first[1])
        resolve_calls = [call for call in client.calls if call[1].endswith("/persona/resolve")]
        self.assertEqual(len(resolve_calls), 1)
