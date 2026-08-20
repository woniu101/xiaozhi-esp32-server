from __future__ import annotations

from datetime import datetime, timezone
import math
import re

from core.companion.semantic_text import semantic_concepts, semantic_tokens
from core.companion.repositories.memory_embedding import MemoryEmbedder, cosine_similarity


def _value(row: dict, snake: str, camel: str, default=None):
    return row.get(snake, row.get(camel, default))


def _freshness(value) -> float:
    if not value:
        return 0.0
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        days = max(0.0, (datetime.now(timezone.utc) - parsed).total_seconds() / 86400)
        return math.exp(-days / 90.0)
    except (TypeError, ValueError):
        return 0.0


def rank_memories(
    rows,
    query: str,
    limit: int,
    exclude_ids: set[int | str] | None = None,
    embedder: MemoryEmbedder | None = None,
) -> list[dict]:
    """Hybrid lexical/concept/recency ranking with subject diversity."""
    normalized_query = str(query or "").lower()
    query_tokens = semantic_tokens(normalized_query)
    query_concepts = semantic_concepts(normalized_query)
    explicit_recall = bool(re.search(r"还?记得|我之前说|上次|你知道我", normalized_query))
    commitment_query = bool(query_concepts & {"plan", "result"})
    excluded = {str(value) for value in (exclude_ids or set())}
    source_rows = [dict(item) for item in rows]
    embeddings: list[list[float]] | None = None
    if embedder is not None and source_rows and normalized_query:
        try:
            documents = [
                f"{_value(row, 'subject_key', 'subjectKey', '')} {row.get('content') or ''}"
                for row in source_rows
            ]
            embeddings = embedder.embed([normalized_query, *documents])
            if len(embeddings) != len(source_rows) + 1:
                embeddings = None
        except Exception:
            embeddings = None
    scored = []

    for index, row in enumerate(source_rows):
        row_id = row.get("id")
        if row_id is not None and str(row_id) in excluded:
            continue
        if str(row.get("sensitivity") or "personal") not in {"public", "personal"}:
            continue
        memory_type = str(_value(row, "memory_type", "memoryType", "semantic"))
        subject_key = str(_value(row, "subject_key", "subjectKey", "") or "")
        content = str(row.get("content") or "").lower()
        content_tokens = semantic_tokens(content)
        lexical = len(query_tokens & content_tokens)
        concept_overlap = len(query_concepts & semantic_concepts(f"{subject_key} {content}"))
        subject_overlap = len(query_tokens & semantic_tokens(subject_key))
        subject_concept_bonus = 0.0
        if subject_key.startswith("identity:") and "identity" in query_concepts:
            subject_concept_bonus = 2.0
        elif subject_key.startswith("preference:") and "preference" in query_concepts:
            subject_concept_bonus = 1.5
        importance = float(row.get("importance") or 0.0)
        confidence = float(row.get("confidence") or 0.0)
        created_at = _value(row, "created_at", "createdAt")
        occurred_at = _value(row, "occurred_at", "occurredAt")
        freshness = _freshness(occurred_at or created_at)
        relevance = (
            lexical * 1.8
            + concept_overlap * 2.6
            + subject_overlap * 1.4
            + subject_concept_bonus
        )
        embedding_similarity = 0.0
        if embeddings is not None:
            embedding_similarity = max(0.0, cosine_similarity(embeddings[0], embeddings[index + 1]))
        embedding_bonus = embedding_similarity * 3.2 if embedding_similarity >= 0.35 else 0.0
        recall_bonus = (
            0.8
            if explicit_recall and importance >= 0.65 and (relevance > 0 or embedding_similarity >= 0.45)
            else 0.0
        )
        commitment_bonus = (
            2.0 if memory_type == "commitment" and commitment_query and relevance > 0 else 0.0
        )
        if relevance <= 0 and embedding_bonus <= 0 and commitment_bonus <= 0:
            continue
        score = (
            relevance
            + embedding_bonus
            + commitment_bonus
            + recall_bonus
            + importance
            + confidence * 0.5
            + freshness * 0.6
        )
        row["memory_type"] = memory_type
        if subject_key:
            row["subject_key"] = subject_key
        if embedding_bonus > 0:
            row["match_source"] = "hybrid_embedding"
            row["embedding_similarity"] = round(embedding_similarity, 4)
        else:
            row["match_source"] = "lexical_concept"
        scored.append((score, row))

    selected = []
    seen_subjects = set()
    for _, row in sorted(scored, key=lambda value: value[0], reverse=True):
        subject = str(row.get("subject_key") or "")
        if subject and subject in seen_subjects:
            continue
        selected.append(row)
        if subject:
            seen_subjects.add(subject)
        if len(selected) >= limit:
            break
    return selected
