from __future__ import annotations

import re


def rank_memories(rows, query: str, limit: int) -> list[dict]:
    normalized_query = (query or "").lower()
    tokens = []
    for token in re.findall(r"[a-z0-9_]{2,}|[\u4e00-\u9fff]{2,}", normalized_query):
        if re.fullmatch(r"[\u4e00-\u9fff]+", token):
            tokens.extend(token[index:index + 2] for index in range(len(token) - 1))
        else:
            tokens.append(token)
    concept_patterns = (
        (r"叫什|名字|称呼", ("被称为", "名字是")),
        (r"喜欢什|爱好|偏好", ("喜欢", "不喜欢")),
        (r"工作|职业|做什么", ("工作是", "职业是")),
    )
    scored = []
    for item in rows:
        row = dict(item)
        if str(row.get("sensitivity") or "personal") not in {"public", "personal"}:
            continue
        if "memory_type" not in row and "memoryType" in row:
            row["memory_type"] = row["memoryType"]
        content = str(row.get("content") or "").lower()
        lexical = sum(1 for token in tokens if token in content)
        for pattern, markers in concept_patterns:
            if re.search(pattern, normalized_query) and any(marker in content for marker in markers):
                lexical += 3
        importance = float(row.get("importance") or 0.0)
        confidence = float(row.get("confidence") or 0.0)
        if lexical > 0 or importance >= 0.9:
            scored.append((lexical * 2 + importance + confidence * 0.5, row))
    return [row for _, row in sorted(scored, key=lambda item: item[0], reverse=True)[:limit]]
