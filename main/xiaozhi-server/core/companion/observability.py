from __future__ import annotations

import threading
from collections import defaultdict
from time import perf_counter
from typing import Any


class CompanionMetrics:
    """Small dependency-free metrics registry for health and Prometheus bridges."""

    def __init__(self):
        self._counters: dict[tuple[str, tuple[tuple[str, str], ...]], float] = defaultdict(float)
        self._durations: dict[tuple[str, tuple[tuple[str, str], ...]], list[float]] = defaultdict(lambda: [0.0, 0.0, 0.0])
        self._lock = threading.Lock()

    @staticmethod
    def _key(name: str, labels: dict[str, Any]):
        return name, tuple(sorted((str(key), str(value)) for key, value in labels.items()))

    def increment(self, name: str, value: float = 1, **labels):
        with self._lock:
            self._counters[self._key(name, labels)] += value

    def observe_ms(self, name: str, duration_ms: float, **labels):
        with self._lock:
            stats = self._durations[self._key(name, labels)]
            stats[0] += max(0.0, duration_ms)
            stats[1] += 1
            stats[2] = max(stats[2], max(0.0, duration_ms))

    def timed(self):
        return perf_counter()

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            counters = [
                {"name": key[0], "labels": dict(key[1]), "value": value}
                for key, value in sorted(self._counters.items())
            ]
            durations = [
                {
                    "name": key[0],
                    "labels": dict(key[1]),
                    "sumMs": round(value[0], 3),
                    "count": int(value[1]),
                    "maxMs": round(value[2], 3),
                }
                for key, value in sorted(self._durations.items())
            ]
        return {"counters": counters, "durations": durations}


metrics = CompanionMetrics()
