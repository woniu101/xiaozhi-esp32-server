from __future__ import annotations

import threading
from pathlib import Path

from config.config_loader import get_project_dir
from core.companion.manager import CompanionManager
from core.companion.persona.manager_api_registry import ManagerApiPersonaRegistry
from core.companion.persona.registry import FilesystemPersonaRegistry
from core.companion.repositories.local_sqlite import SQLiteCompanionRepository
from core.companion.repositories.manager_api import ManagerApiCompanionRepository


_MANAGERS: dict[tuple[str, str, str, str, int, int], CompanionManager] = {}
_LOCK = threading.Lock()


def _project_path(value: str, default: str) -> Path:
    path = Path(value or default).expanduser()
    if not path.is_absolute():
        path = Path(get_project_dir()) / path
    return path.resolve()


def get_companion_manager(config: dict) -> CompanionManager:
    companion = config.get("companion", {})
    registry_path = _project_path(companion.get("persona_registry", ""), "data/companion/personas")
    database_path = _project_path(companion.get("database_path", ""), "data/companion/companion.db")
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
    key = (str(registry_path), registry_backend, backend, str(database_path), cache_ttl, latest_ttl)
    with _LOCK:
        manager = _MANAGERS.get(key)
        if manager is None:
            repository = (
                ManagerApiCompanionRepository()
                if backend == "manager-api"
                else SQLiteCompanionRepository(database_path)
            )
            manager = CompanionManager(
                ManagerApiPersonaRegistry(cache_ttl, latest_ttl)
                if registry_backend == "manager-api"
                else FilesystemPersonaRegistry(registry_path),
                repository,
            )
            _MANAGERS[key] = manager
        return manager
