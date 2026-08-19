from __future__ import annotations

import contextlib
import shutil
import stat
import tempfile
import zipfile
from pathlib import Path, PurePosixPath


ALLOWED_FILES = {"manifest.json", "meta.json", "persona.md", "work.md", "SKILL.md"}
MAX_FILES = 128
MAX_FILE_BYTES = 2 * 1024 * 1024
MAX_TOTAL_BYTES = 8 * 1024 * 1024


class UnsafePersonaSource(ValueError):
    pass


def _validate_member(name: str) -> PurePosixPath:
    normalized = name.replace("\\", "/")
    path = PurePosixPath(normalized)
    if path.is_absolute() or ".." in path.parts:
        raise UnsafePersonaSource(f"压缩包包含不安全路径: {name}")
    if not path.parts:
        raise UnsafePersonaSource("压缩包包含空路径")
    return path


def _is_symlink(info: zipfile.ZipInfo) -> bool:
    mode = (info.external_attr >> 16) & 0xFFFF
    return stat.S_ISLNK(mode)


@contextlib.contextmanager
def materialize_source(source_path: str | Path):
    source = Path(source_path).expanduser().resolve()
    if source.is_dir():
        yield source
        return
    if not source.is_file() or source.suffix.lower() != ".zip":
        raise UnsafePersonaSource("人物来源必须是目录或 ZIP 文件")

    temp_dir = Path(tempfile.mkdtemp(prefix="cyber-persona-"))
    try:
        with zipfile.ZipFile(source) as archive:
            members = archive.infolist()
            if len(members) > MAX_FILES:
                raise UnsafePersonaSource(f"压缩包文件数超过限制: {MAX_FILES}")
            total_size = 0
            for member in members:
                member_path = _validate_member(member.filename)
                if _is_symlink(member):
                    raise UnsafePersonaSource(f"压缩包不允许符号链接: {member.filename}")
                if member.file_size > MAX_FILE_BYTES:
                    raise UnsafePersonaSource(f"文件超过大小限制: {member.filename}")
                total_size += member.file_size
                if total_size > MAX_TOTAL_BYTES:
                    raise UnsafePersonaSource("压缩包解压后总体积超过限制")
                target = (temp_dir / Path(*member_path.parts)).resolve()
                if temp_dir not in target.parents and target != temp_dir:
                    raise UnsafePersonaSource(f"压缩路径逃逸: {member.filename}")
            archive.extractall(temp_dir)

        roots = [path.parent for path in temp_dir.rglob("manifest.json")]
        if len(roots) == 1:
            yield roots[0]
        else:
            yield temp_dir
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def locate_artifacts(root: Path) -> dict[str, Path]:
    artifacts: dict[str, Path] = {}
    for name in ALLOWED_FILES:
        direct = root / name
        matches = [direct] if direct.is_file() else list(root.rglob(name))
        if len(matches) > 1:
            raise UnsafePersonaSource(f"发现多份 {name}，无法确定人物根目录")
        if matches:
            candidate = matches[0].resolve()
            if root.resolve() not in candidate.parents and candidate != root.resolve():
                raise UnsafePersonaSource(f"人物文件越出来源目录: {name}")
            if candidate.is_symlink():
                raise UnsafePersonaSource(f"人物文件不允许符号链接: {name}")
            if candidate.stat().st_size > MAX_FILE_BYTES:
                raise UnsafePersonaSource(f"人物文件超过大小限制: {name}")
            artifacts[name] = candidate
    return artifacts
