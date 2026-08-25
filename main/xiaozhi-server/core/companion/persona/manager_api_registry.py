from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from config.manage_api_client import ManageApiClient
from core.companion.models import PersonaSpec
from core.companion.observability import metrics


@dataclass
class _CacheEntry:
    spec: PersonaSpec
    prompt: str
    metadata: dict[str, Any]
    expires_at: float
    stale_until: float


class ManagerApiPersonaRegistry:
    """Resolve published Persona versions from manager-api with fail-open stale cache."""

    def __init__(
        self,
        ttl_seconds: int = 600,
        latest_ttl_seconds: int = 60,
        stale_seconds: int = 3600,
        client=None,
    ):
        self.ttl_seconds = max(1, int(ttl_seconds))
        self.latest_ttl_seconds = max(1, int(latest_ttl_seconds))
        self.stale_seconds = max(self.ttl_seconds, int(stale_seconds))
        self._cache: dict[tuple[str, str | None, str | None], _CacheEntry] = {}
        self._configured_client = client

    def _client(self):
        if self._configured_client is not None:
            return self._configured_client
        if ManageApiClient._instance is None:
            raise RuntimeError("manager-api client 尚未初始化")
        return ManageApiClient._instance

    def evict(self, persona_id: str) -> int:
        keys = [key for key in self._cache if key[0] == persona_id]
        for key in keys:
            self._cache.pop(key, None)
        return len(keys)

    async def load_for_runtime(
        self,
        persona_id: str,
        version: str | None = None,
        agent_id: str | None = None,
    ) -> tuple[PersonaSpec, str, dict]:
        if not agent_id:
            raise ValueError("manager-api Persona 解析必须提供 agent_id")
        key = (persona_id, version or None, agent_id)
        now = time.monotonic()
        cached = self._cache.get(key)
        if cached and cached.expires_at > now:
            metrics.increment("companion_persona_cache_hit_total")
            return cached.spec, cached.prompt, dict(cached.metadata)

        metrics.increment("companion_persona_cache_miss_total")
        started = time.perf_counter()

        payload = {
            "agentId": agent_id,
            "personaId": persona_id,
            "version": version,
            "knownArtifactHash": cached.metadata.get("artifact_sha256") if cached else None,
        }
        try:
            value = await self._client()._execute_async_request(
                "POST", "/config/companion/persona/resolve", json=payload
            )
            if value.get("notModified"):
                if not cached:
                    raise RuntimeError("manager-api 返回 notModified，但本地没有 Persona 缓存")
                cached.expires_at = now + (self.latest_ttl_seconds if version is None else self.ttl_seconds)
                metrics.observe_ms(
                    "companion_persona_resolve_duration_ms",
                    (time.perf_counter() - started) * 1000,
                    backend="manager-api",
                    status="not_modified",
                )
                return cached.spec, cached.prompt, dict(cached.metadata)
            raw_spec = value.get("canonicalSpec")
            if isinstance(raw_spec, str):
                import json

                raw_spec = json.loads(raw_spec)
            if not isinstance(raw_spec, dict):
                raise ValueError("manager-api 未返回合法 PersonaSpec")
            prompt = str(value.get("runtimePrompt") or "")
            resolved_version = str(value.get("version") or version or "")
            artifact_hash = str(value.get("artifactHash") or "")
            if not prompt or not resolved_version or len(artifact_hash) != 64:
                raise ValueError("manager-api 返回的 Persona 版本数据不完整")
            spec = PersonaSpec.from_dict(raw_spec)
            metadata = {
                "persona_id": persona_id,
                "version": resolved_version,
                "status": "published",
                "artifact_sha256": artifact_hash,
                "compiler_version": value.get("compilerVersion") or "",
            }
            ttl = self.latest_ttl_seconds if version is None else self.ttl_seconds
            entry = _CacheEntry(spec, prompt, metadata, now + ttl, now + self.stale_seconds)
            self._cache[key] = entry
            metrics.observe_ms(
                "companion_persona_resolve_duration_ms",
                (time.perf_counter() - started) * 1000,
                backend="manager-api",
                status="success",
            )
            return spec, prompt, dict(metadata)
        except Exception:
            if cached and cached.stale_until > now:
                metrics.observe_ms(
                    "companion_persona_resolve_duration_ms",
                    (time.perf_counter() - started) * 1000,
                    backend="manager-api",
                    status="stale",
                )
                return cached.spec, cached.prompt, dict(cached.metadata)
            metrics.observe_ms(
                "companion_persona_resolve_duration_ms",
                (time.perf_counter() - started) * 1000,
                backend="manager-api",
                status="failed",
            )
            raise

    def invalidate(self, persona_id: str, version: str | None = None):
        for key in list(self._cache):
            if key[0] == persona_id and (version is None or key[1] == version):
                self._cache.pop(key, None)
