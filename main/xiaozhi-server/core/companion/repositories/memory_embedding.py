from __future__ import annotations

from collections import OrderedDict
import hashlib
import math
from threading import Lock
from typing import Any, Protocol
from urllib.parse import urlparse

import requests


class MemoryEmbedder(Protocol):
    def embed(self, texts: list[str]) -> list[list[float]]:
        ...


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    numerator = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm <= 0 or right_norm <= 0:
        return 0.0
    return max(-1.0, min(1.0, numerator / (left_norm * right_norm)))


class OpenAICompatibleMemoryEmbedder:
    """Small cached adapter for local or OpenAI-compatible embedding services."""

    def __init__(self, config: dict[str, Any] | None):
        value = config if isinstance(config, dict) else {}
        self.enabled = bool(value.get("enabled", False))
        self.base_url = str(value.get("base_url") or "").rstrip("/")
        self.api_key = str(value.get("api_key") or "")
        self.model = str(value.get("model") or "")
        self.timeout = max(1, min(10, int(value.get("timeout_seconds") or 3)))
        self.cache_size = max(100, min(10000, int(value.get("cache_size") or 2000)))
        self._cache: OrderedDict[str, list[float]] = OrderedDict()
        self._lock = Lock()

    @classmethod
    def from_config(cls, config: dict[str, Any] | None) -> "OpenAICompatibleMemoryEmbedder | None":
        instance = cls(config)
        if not instance.enabled:
            return None
        parsed = urlparse(instance.base_url)
        local_http = parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "localhost", "::1"}
        if (parsed.scheme != "https" and not local_http) or not parsed.hostname or not instance.model:
            raise ValueError("Companion memory_embedding 需要 HTTPS（或本机 HTTP）地址和模型名称")
        return instance

    def embed(self, texts: list[str]) -> list[list[float]]:
        bounded = [str(text or "")[:2000] for text in texts]
        keys = [hashlib.sha256(text.encode("utf-8")).hexdigest() for text in bounded]
        result: list[list[float] | None] = [None] * len(bounded)
        missing_texts: list[str] = []
        missing_indexes: list[int] = []
        with self._lock:
            for index, key in enumerate(keys):
                cached = self._cache.get(key)
                if cached is not None:
                    self._cache.move_to_end(key)
                    result[index] = cached
                else:
                    missing_texts.append(bounded[index])
                    missing_indexes.append(index)

        if missing_texts:
            headers = {"Content-Type": "application/json"}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"
            response = requests.post(
                self.base_url + "/embeddings",
                headers=headers,
                json={"model": self.model, "input": missing_texts},
                timeout=self.timeout,
                allow_redirects=False,
            )
            response.raise_for_status()
            data = response.json().get("data") or []
            vectors = {
                int(item.get("index", index)): [float(value) for value in item.get("embedding", [])]
                for index, item in enumerate(data)
                if isinstance(item, dict)
            }
            if len(vectors) != len(missing_texts) or any(not vector for vector in vectors.values()):
                raise ValueError("Embedding 服务返回了不完整的向量")
            with self._lock:
                for missing_index, result_index in enumerate(missing_indexes):
                    vector = vectors[missing_index]
                    result[result_index] = vector
                    self._cache[keys[result_index]] = vector
                    self._cache.move_to_end(keys[result_index])
                while len(self._cache) > self.cache_size:
                    self._cache.popitem(last=False)

        return [vector or [] for vector in result]
