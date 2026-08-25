from __future__ import annotations

import threading
import json
from pathlib import Path

from config.config_loader import get_project_dir
from core.companion.manager import CompanionManager
from core.companion.persona.manager_api_registry import ManagerApiPersonaRegistry
from core.companion.persona.registry import FilesystemPersonaRegistry
from core.companion.repositories.local_sqlite import SQLiteCompanionRepository
from core.companion.repositories.manager_api import ManagerApiCompanionRepository
from core.companion.repositories.memory_embedding import OpenAICompatibleMemoryEmbedder
from core.companion.proactive import proactive_registry


_MANAGERS: dict[tuple[str, str, str, str, str, int, int, str], CompanionManager] = {}
_LOCK = threading.Lock()


def companion_runtime_health() -> dict:
    """Return aggregate runtime health without exposing user or Persona identifiers."""
    with _LOCK:
        managers = list(_MANAGERS.values())
    outboxes = {}
    for manager in managers:
        outbox = getattr(getattr(manager, "repository", None), "outbox", None)
        if outbox is not None:
            outboxes[str(outbox.path)] = outbox
    pending = 0
    oldest = 0.0
    for outbox in outboxes.values():
        try:
            pending += outbox.count()
            oldest = max(oldest, outbox.oldest_age_seconds())
        except Exception:
            continue
    return {
        "managerCount": len(managers),
        "outboxPending": pending,
        "outboxOldestSeconds": round(oldest, 3),
        "proactive": proactive_registry.summary(),
    }


def evict_companion_persona(persona_id: str) -> int:
    """Evict a Persona from all manager-api registries for future sessions."""
    with _LOCK:
        managers = list(_MANAGERS.values())
    evicted = 0
    for manager in managers:
        registry = getattr(manager, "persona_registry", None)
        callback = getattr(registry, "evict", None)
        if callable(callback):
            evicted += int(callback(persona_id) or 0)
    return evicted


def _project_path(value: str, default: str) -> Path:
    path = Path(value or default).expanduser()
    if not path.is_absolute():
        path = Path(get_project_dir()) / path
    return path.resolve()


def get_companion_manager(config: dict) -> CompanionManager:
    companion = config.get("companion", {})
    registry_path = _project_path(companion.get("persona_registry", ""), "data/companion/personas")
    database_path = _project_path(companion.get("database_path", ""), "data/companion/companion.db")
    outbox_path = _project_path(companion.get("outbox_path", ""), "data/companion/commit_outbox.db")
    backend = str(companion.get("repository") or "auto").lower()
    if backend == "auto":
        backend = "manager-api" if config.get("read_config_from_api", False) else "sqlite"
    registry_backend = str(companion.get("persona_registry_backend") or "auto").lower()
    if registry_backend == "auto":
        registry_backend = "manager-api" if config.get("read_config_from_api", False) else "filesystem"
    if backend not in {"manager-api", "sqlite"}:
        raise ValueError(f"不支持的 Companion repository: {backend}")
    if registry_backend not in {"manager-api", "filesystem"}:
        raise ValueError(f"不支持的 Persona Registry: {registry_backend}")
    cache_ttl = int(companion.get("persona_cache_ttl_seconds") or 600)
    latest_ttl = int(companion.get("persona_latest_ttl_seconds") or 60)
    embedding_config = companion.get("memory_embedding") or {}
    embedding_key = json.dumps(embedding_config, sort_keys=True, default=str)
    key = (
        str(registry_path), registry_backend, backend, str(database_path), str(outbox_path),
        cache_ttl, latest_ttl, embedding_key,
    )
    with _LOCK:
        manager = _MANAGERS.get(key)
        if manager is None:
            embedder = OpenAICompatibleMemoryEmbedder.from_config(embedding_config)
            repository = (
                ManagerApiCompanionRepository(embedder, outbox_path)
                if backend == "manager-api"
                else SQLiteCompanionRepository(database_path, embedder)
            )
            manager = CompanionManager(
                ManagerApiPersonaRegistry(cache_ttl, latest_ttl)
                if registry_backend == "manager-api"
                else FilesystemPersonaRegistry(registry_path),
                repository,
            )
            _MANAGERS[key] = manager
        return manager
