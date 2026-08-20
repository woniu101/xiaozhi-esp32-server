from __future__ import annotations

from dataclasses import dataclass, field
from time import perf_counter
from typing import Any

from core.companion.observability import metrics


def should_drop_audio(
    sentence_id: str | None,
    current_sentence_id: str | None,
    aborted_sentence_ids: set[str] | None = None,
) -> bool:
    if sentence_id is None:
        return False
    return sentence_id != current_sentence_id or sentence_id in (aborted_sentence_ids or set())


@dataclass
class ConversationLatencyTracker:
    transport_id: str
    started_at: float = field(default_factory=perf_counter)
    stages: dict[str, float] = field(default_factory=dict)
    _observed: set[str] = field(default_factory=set)

    def __post_init__(self):
        self.stages.setdefault("asr_final", self.started_at)

    def mark(self, stage: str, at: float | None = None):
        if stage not in self.stages:
            self.stages[stage] = at if at is not None else perf_counter()
        self._observe(stage)

    def abort(self, started_at: float):
        self.mark("interrupt_stop")
        if "interrupt" not in self._observed:
            metrics.observe_ms(
                "companion_voice_interrupt_stop_ms",
                (self.stages["interrupt_stop"] - started_at) * 1000,
            )
            self._observed.add("interrupt")

    def complete(self):
        self.mark("completed")
        if "total" not in self._observed:
            metrics.observe_ms(
                "companion_voice_turn_total_ms",
                (self.stages["completed"] - self.started_at) * 1000,
            )
            self._observed.add("total")

    def snapshot(self) -> dict[str, Any]:
        origin = self.stages.get("asr_final", self.started_at)
        values = {
            f"{name}Ms": round(max(0.0, (timestamp - origin) * 1000), 3)
            for name, timestamp in self.stages.items()
            if name != "asr_final"
        }
        values["transportId"] = self.transport_id
        return values

    def _observe(self, stage: str):
        origin = self.stages.get("asr_final", self.started_at)
        mapping = {
            "llm_first_token": "companion_voice_asr_to_llm_first_token_ms",
            "tts_text_enqueued": "companion_voice_asr_to_tts_text_ms",
            "first_audio": "companion_voice_asr_to_first_audio_ms",
        }
        metric_name = mapping.get(stage)
        if metric_name and stage not in self._observed:
            metrics.observe_ms(metric_name, (self.stages[stage] - origin) * 1000)
            self._observed.add(stage)
