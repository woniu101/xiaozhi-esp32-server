from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from difflib import unified_diff
from pathlib import Path
from typing import Any

from core.companion.models import PersonaSpec, ValidationReport


SAFE_COMPONENT_RE = re.compile(r"[^a-zA-Z0-9._-]+")


def _safe_component(value: str) -> str:
    safe = SAFE_COMPONENT_RE.sub("_", value).strip("._")
    if not safe:
        raise ValueError("无效的人物或版本标识")
    return safe


def _json_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")


def _atomic_write(path: Path, data: bytes):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


@dataclass
class PersonaVersionRecord:
    persona_id: str
    version: str
    status: str
    artifact_sha256: str
    path: Path


class FilesystemPersonaRegistry:
    def __init__(self, base_dir: str | Path):
        self.base_dir = Path(base_dir).expanduser().resolve()
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _persona_dir(self, persona_id: str) -> Path:
        return self.base_dir / _safe_component(persona_id)

    def _version_dir(self, persona_id: str, version: str) -> Path:
        return self._persona_dir(persona_id) / "versions" / _safe_component(version)

    def save(
        self,
        spec: PersonaSpec,
        runtime_prompt: str,
        report: ValidationReport,
        artifact_sha256: str,
        version: str,
        status: str = "draft",
    ) -> PersonaVersionRecord:
        if status not in {"draft", "published", "archived"}:
            raise ValueError(f"无效状态: {status}")
        if not re.fullmatch(r"[a-fA-F0-9]{64}", artifact_sha256 or ""):
            raise ValueError("artifact_sha256 必须是 64 位 SHA-256")
        if spec.source.get("artifact_sha256") != artifact_sha256:
            raise ValueError("PersonaSpec 来源哈希与导入制品哈希不一致")
        target = self._version_dir(spec.id, version)
        metadata_path = target / "version.json"
        if metadata_path.exists():
            existing = json.loads(metadata_path.read_text(encoding="utf-8"))
            if existing.get("artifact_sha256") != artifact_sha256:
                raise ValueError(f"版本 {version} 已存在且内容不同，请使用新版本号")
            return PersonaVersionRecord(spec.id, version, existing.get("status", "draft"), artifact_sha256, target)

        now = datetime.now(timezone.utc).isoformat()
        metadata = {
            "persona_id": spec.id,
            "version": version,
            "status": status,
            "artifact_sha256": artifact_sha256,
            "created_at": now,
            "compiler_version": "cyber-persona-compiler/1",
        }
        _atomic_write(target / "persona.json", _json_bytes(spec.to_dict()))
        _atomic_write(target / "runtime_prompt.txt", runtime_prompt.encode("utf-8"))
        _atomic_write(target / "validation.json", _json_bytes(report.to_dict()))
        _atomic_write(metadata_path, _json_bytes(metadata))
        if status == "published":
            self.publish(spec.id, version)
        return PersonaVersionRecord(spec.id, version, status, artifact_sha256, target)

    def load(self, persona_id: str, version: str | None = None) -> tuple[PersonaSpec, str, dict]:
        if version is None:
            pointer = self.get_published(persona_id)
            if not pointer:
                raise FileNotFoundError(f"人物 {persona_id} 尚未发布版本")
            version = pointer["version"]
        target = self._version_dir(persona_id, version)
        spec = PersonaSpec.from_dict(json.loads((target / "persona.json").read_text(encoding="utf-8")))
        prompt = (target / "runtime_prompt.txt").read_text(encoding="utf-8")
        metadata = json.loads((target / "version.json").read_text(encoding="utf-8"))
        return spec, prompt, metadata

    def load_for_runtime(
        self,
        persona_id: str,
        version: str | None = None,
        agent_id: str | None = None,
    ) -> tuple[PersonaSpec, str, dict]:
        del agent_id
        spec, prompt, metadata = self.load(persona_id, version)
        if metadata.get("status") != "published":
            raise ValueError(f"人物版本尚未发布，不能用于运行时: {persona_id}@{metadata.get('version')}")
        return spec, prompt, metadata

    def publish(self, persona_id: str, version: str):
        target = self._version_dir(persona_id, version)
        metadata_path = target / "version.json"
        if not metadata_path.exists():
            raise FileNotFoundError(f"人物版本不存在: {persona_id}@{version}")
        report = json.loads((target / "validation.json").read_text(encoding="utf-8"))
        if not report.get("valid", False):
            raise ValueError("不能发布校验失败的人物版本")
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        metadata["status"] = "published"
        metadata["published_at"] = datetime.now(timezone.utc).isoformat()
        _atomic_write(metadata_path, _json_bytes(metadata))
        pointer = {
            "persona_id": persona_id,
            "version": version,
            "artifact_sha256": metadata["artifact_sha256"],
            "published_at": metadata["published_at"],
        }
        _atomic_write(self._persona_dir(persona_id) / "published.json", _json_bytes(pointer))

    def rollback(self, persona_id: str, version: str):
        self.publish(persona_id, version)

    def archive(self, persona_id: str, version: str):
        target = self._version_dir(persona_id, version)
        metadata_path = target / "version.json"
        if not metadata_path.exists():
            raise FileNotFoundError(f"人物版本不存在: {persona_id}@{version}")
        published = self.get_published(persona_id)
        if published and published.get("version") == version:
            raise ValueError("不能归档当前发布版本，请先发布或回滚到其他版本")
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        metadata["status"] = "archived"
        metadata["archived_at"] = datetime.now(timezone.utc).isoformat()
        _atomic_write(metadata_path, _json_bytes(metadata))

    def personas(self) -> list[dict]:
        result = []
        for path in sorted(self.base_dir.iterdir()):
            if not path.is_dir():
                continue
            published = self.get_published(path.name)
            result.append(
                {
                    "persona_id": path.name,
                    "versions": self.versions(path.name),
                    "published": published.get("version") if published else None,
                }
            )
        return result

    def get_published(self, persona_id: str) -> dict | None:
        path = self._persona_dir(persona_id) / "published.json"
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None

    def versions(self, persona_id: str) -> list[str]:
        versions_dir = self._persona_dir(persona_id) / "versions"
        if not versions_dir.exists():
            return []
        return sorted(path.name for path in versions_dir.iterdir() if path.is_dir())

    def diff(self, persona_id: str, left: str, right: str) -> str:
        left_spec, _, _ = self.load(persona_id, left)
        right_spec, _, _ = self.load(persona_id, right)
        left_lines = _json_bytes(left_spec.to_dict()).decode("utf-8").splitlines(keepends=True)
        right_lines = _json_bytes(right_spec.to_dict()).decode("utf-8").splitlines(keepends=True)
        return "".join(unified_diff(left_lines, right_lines, fromfile=left, tofile=right))


def content_hash(files: dict[str, bytes]) -> str:
    digest = hashlib.sha256()
    for name in sorted(files):
        digest.update(name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(files[name])
        digest.update(b"\0")
    return digest.hexdigest()
