import asyncio
from pathlib import Path
import tempfile
import unittest

from core.companion.repositories.commit_outbox import DurableCommitOutbox
from core.companion.repositories.manager_api import ManagerApiCompanionRepository
from core.companion.state_models import (
    CompanionEvent,
    CompanionIdentity,
    CompanionState,
    MemoryCandidate,
)


class FakeOutboxClient:
    def __init__(self):
        self.fail_live_commit = False
        self.conflict_once = False
        self.commit_payloads = []
        self.remote_state = CompanionState(revision=5).to_dict()

    async def _execute_async_request(self, method, endpoint, **kwargs):
        if endpoint.endswith("/commit") and self.fail_live_commit:
            raise ConnectionError("manager-api unavailable")
        return await self._async_request(method, endpoint, **kwargs)

    async def _async_request(self, method, endpoint, **kwargs):
        if endpoint.endswith("/state"):
            return self.remote_state
        if endpoint.endswith("/commit"):
            payload = kwargs["json"]
            self.commit_payloads.append(payload)
            if self.conflict_once:
                self.conflict_once = False
                return "conflict"
            return "committed"
        return []


class TestOutboxRepository(ManagerApiCompanionRepository):
    def __init__(self, client, outbox_path):
        super().__init__(outbox_path=outbox_path)
        self.client = client

    def _client(self):
        return self.client


class CommitOutboxTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "commit-outbox.db"
        self.identity = CompanionIdentity("user-1", "agent-1", "persona-1")

    def tearDown(self):
        self.temp.cleanup()

    def test_rows_survive_repository_recreation(self):
        payload = self._payload("turn-persist")
        DurableCommitOutbox(self.path).enqueue(payload, "offline")

        reopened = DurableCommitOutbox(self.path)

        self.assertEqual(reopened.count("user-1", "agent-1", "persona-1"), 1)
        self.assertEqual(reopened.due(force=True)[0]["payload"]["turnId"], "turn-persist")
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)
        self.assertGreaterEqual(reopened.oldest_age_seconds(), 0)
        with reopened._connect() as connection:
            self.assertEqual("delete", connection.execute("PRAGMA journal_mode").fetchone()[0])

    def test_failed_live_commit_is_queued_then_delivered(self):
        asyncio.run(self._failed_live_commit_is_queued_then_delivered())

    async def _failed_live_commit_is_queued_then_delivered(self):
        client = FakeOutboxClient()
        client.fail_live_commit = True
        repository = TestOutboxRepository(client, self.path)
        repository._schedule_drain = lambda: None
        state = CompanionState(revision=1)

        result = await repository.commit_turn(
            self.identity,
            "turn-queued",
            0,
            state,
            [CompanionEvent("user_showed_care", 0.8)],
            [MemoryCandidate("semantic", "用户喜欢咖啡", 0.7, 0.8)],
            {"meaningfulTurn": True, "allowedStages": ["familiar", "friend"]},
        )

        self.assertEqual(result, "queued")
        self.assertTrue(await repository.has_pending_commits(self.identity))
        client.fail_live_commit = False
        self.assertEqual(await repository.flush_pending(force=True), 1)
        self.assertFalse(await repository.has_pending_commits(self.identity))

    def test_conflicting_pending_commit_is_rebased_before_delivery(self):
        asyncio.run(self._conflicting_pending_commit_is_rebased_before_delivery())

    async def _conflicting_pending_commit_is_rebased_before_delivery(self):
        client = FakeOutboxClient()
        client.conflict_once = True
        repository = TestOutboxRepository(client, self.path)
        repository.outbox.enqueue(self._payload("turn-rebase"), "offline")

        delivered = await repository.flush_pending(force=True)

        self.assertEqual(delivered, 1)
        rebased = client.commit_payloads[-1]
        self.assertEqual(rebased["expectedRevision"], 5)
        self.assertEqual(rebased["state"]["revision"], 6)
        self.assertAlmostEqual(rebased["state"]["emotion"]["warmth"], 0.516, places=3)
        self.assertTrue(rebased["diagnostic"]["outboxRebased"])

    def _payload(self, turn_id):
        state = CompanionState(revision=1)
        return {
            "userId": self.identity.user_id,
            "agentId": self.identity.agent_id,
            "personaId": self.identity.persona_id,
            "turnId": turn_id,
            "expectedRevision": 0,
            "state": state.to_dict(),
            "events": [
                {"eventType": "user_showed_care", "confidence": 0.8, "payload": {}}
            ],
            "memories": [],
            "diagnostic": {
                "meaningfulTurn": True,
                "allowedStages": ["familiar", "friend"],
                "emotionProfile": {"reactivity": 0.4},
            },
        }


if __name__ == "__main__":
    unittest.main()
