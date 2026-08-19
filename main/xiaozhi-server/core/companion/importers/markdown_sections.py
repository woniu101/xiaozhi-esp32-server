from __future__ import annotations

import re
from dataclasses import dataclass


HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
BULLET_RE = re.compile(r"^\s*(?:[-*+] |\d+[.)]\s+)(.+?)\s*$")


@dataclass
class MarkdownSection:
    title: str
    level: int
    content: str
    parent_titles: tuple[str, ...] = ()

    @property
    def normalized_title(self) -> str:
        return normalize_title(self.title)


def normalize_title(title: str) -> str:
    title = re.sub(r"[`*_]", "", title).strip().lower()
    title = re.sub(r"^layer\s*\d+\s*[:：-]?\s*", "", title)
    title = re.sub(r"^第?[零一二三四五六七八九十0-9]+层\s*[:：-]?\s*", "", title)
    title = re.sub(r"\s+", " ", title)
    return title


def parse_sections(markdown: str) -> list[MarkdownSection]:
    lines = markdown.splitlines()
    result: list[MarkdownSection] = []
    stack: list[tuple[int, str]] = []
    current_title = "document"
    current_level = 0
    current_parent: tuple[str, ...] = ()
    buffer: list[str] = []

    def flush():
        nonlocal buffer
        if current_title != "document" or any(line.strip() for line in buffer):
            result.append(
                MarkdownSection(
                    title=current_title,
                    level=current_level,
                    content="\n".join(buffer).strip(),
                    parent_titles=current_parent,
                )
            )
        buffer = []

    for line in lines:
        match = HEADING_RE.match(line)
        if not match:
            buffer.append(line)
            continue
        flush()
        current_level = len(match.group(1))
        current_title = match.group(2).strip()
        while stack and stack[-1][0] >= current_level:
            stack.pop()
        current_parent = tuple(title for _, title in stack)
        stack.append((current_level, current_title))
    flush()
    return result


def find_section(sections: list[MarkdownSection], *aliases: str) -> MarkdownSection | None:
    normalized_aliases = [normalize_title(alias) for alias in aliases]
    for section in sections:
        title = section.normalized_title
        if title in normalized_aliases:
            return section
    for section in sections:
        title = section.normalized_title
        if any(alias in title for alias in normalized_aliases):
            return section
    return None


def find_sections(sections: list[MarkdownSection], *aliases: str) -> list[MarkdownSection]:
    normalized_aliases = [normalize_title(alias) for alias in aliases]
    return [
        section
        for section in sections
        if any(alias == section.normalized_title or alias in section.normalized_title for alias in normalized_aliases)
    ]


def bullets(content: str) -> list[str]:
    values = []
    for line in content.splitlines():
        match = BULLET_RE.match(line)
        if match:
            value = match.group(1).strip()
            if value and not value.startswith("{"):
                values.append(value)
    return values


def prose(content: str) -> str:
    values = []
    in_fence = False
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence or not stripped or stripped == "---" or BULLET_RE.match(line):
            continue
        if stripped.startswith(">"):
            stripped = stripped.lstrip("> ")
        values.append(stripped)
    return " ".join(values).strip()
