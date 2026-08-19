from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import math

from core.companion.state_models import CompanionEvent, RelationshipState, iso_now


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


class RelationshipEngine:
    EVENT_DELTAS = {
        "user_showed_care": {"trust": 0.015, "affection": 0.025},
        "user_expressed_gratitude": {"trust": 0.01, "affection": 0.015},
        "user_insulted_companion": {"trust": -0.05, "affection": -0.03, "conflict": 0.08},
        "user_apologized": {"trust": 0.015, "conflict": -0.06},
        "shared_plan_created": {"trust": 0.01, "intimacy": 0.015},
        "meaningful_disclosure": {"trust": 0.02, "intimacy": 0.02},
    }
    STAGE_RULES = (
        ("familiar", "friend", 20, 0.48, 0.45, 0.35, 1),
        ("friend", "ambiguous", 60, 0.65, 0.62, 0.30, 4),
        ("ambiguous", "lover", 120, 0.78, 0.75, 0.22, 8),
        ("lover", "intimate", 240, 0.88, 0.86, 0.18, 15),
    )
    STAGE_ORDER = ("stranger", "familiar", "friend", "ambiguous", "lover", "intimate")

    def decay(self, state: RelationshipState, now: datetime | None = None) -> RelationshipState:
        """Cool volatile conflict and gently reduce unsupported closeness over long inactivity."""
        now = now or datetime.now(timezone.utc)
        try:
            updated = datetime.fromisoformat(state.updated_at)
            if updated.tzinfo is None:
                updated = updated.replace(tzinfo=timezone.utc)
        except (TypeError, ValueError):
            updated = now
        hours = max(0.0, (now - updated).total_seconds() / 3600.0)
        values = {
            "conflict": state.conflict * math.pow(0.5, hours / 72.0),
            "trust": 0.3 + (state.trust - 0.3) * math.pow(0.5, hours / (24.0 * 180)),
            "affection": 0.3 + (state.affection - 0.3) * math.pow(0.5, hours / (24.0 * 90)),
            "intimacy": 0.15 + (state.intimacy - 0.15) * math.pow(0.5, hours / (24.0 * 60)),
        }
        cooled = replace(state, **{key: _clamp(value) for key, value in values.items()}, updated_at=now.isoformat())
        return replace(cooled, stage=self._stable_stage(cooled))

    def apply(
        self,
        state: RelationshipState,
        events: list[CompanionEvent],
        meaningful_turn: bool,
        allowed_stages: list[str] | None = None,
    ) -> RelationshipState:
        values = {name: getattr(state, name) for name in ("trust", "affection", "intimacy", "conflict")}
        shared_delta = 0
        for event in events:
            if event.confidence < 0.6:
                continue
            for name, delta in self.EVENT_DELTAS.get(event.event_type, {}).items():
                values[name] = _clamp(values[name] + max(-0.08, min(0.08, delta * event.confidence)))
            if event.event_type == "shared_plan_created":
                shared_delta += 1
        result = replace(
            state,
            **values,
            meaningful_turns=state.meaningful_turns + (1 if meaningful_turn else 0),
            shared_event_count=state.shared_event_count + shared_delta,
            updated_at=iso_now(),
        )
        stable = replace(result, stage=self._stable_stage(result))
        return replace(stable, stage=self._next_stage(stable, allowed_stages))

    def _stable_stage(self, state: RelationshipState) -> str:
        downgrade_rules = {
            "intimate": ("lover", 0.76, 0.74, 0.48),
            "lover": ("ambiguous", 0.64, 0.60, 0.55),
            "ambiguous": ("friend", 0.50, 0.46, 0.62),
            "friend": ("familiar", 0.34, 0.32, 0.72),
            "familiar": ("stranger", 0.18, 0.18, 0.82),
        }
        rule = downgrade_rules.get(state.stage)
        if not rule:
            return state.stage
        target, min_trust, min_affection, max_conflict = rule
        if state.trust < min_trust or state.affection < min_affection or state.conflict > max_conflict:
            return target
        return state.stage

    def _next_stage(self, state: RelationshipState, allowed_stages: list[str] | None) -> str:
        allowed = set(allowed_stages or ["familiar", "friend", "ambiguous", "lover", "intimate"])
        for current, target, turns, trust, affection, max_conflict, shared in self.STAGE_RULES:
            if state.stage != current or target not in allowed:
                continue
            if (
                state.meaningful_turns >= turns
                and state.trust >= trust
                and state.affection >= affection
                and state.conflict <= max_conflict
                and state.shared_event_count >= shared
            ):
                return target
        return state.stage

    def describe(self, state: RelationshipState) -> str:
        stage_text = {
            "stranger": "彼此还很陌生，保持礼貌和边界",
            "familiar": "已经比较熟悉，可以自然交流，但不过度亲密",
            "friend": "关系像熟悉的朋友，会主动关心但尊重空间",
            "ambiguous": "彼此有明显好感，可以含蓄亲近但不强迫关系定义",
            "lover": "关系稳定亲密，表达自然且重视承诺",
            "intimate": "关系高度亲密，有深厚共同经历，但仍尊重边界",
        }.get(state.stage, "关系保持自然和尊重")
        if state.conflict >= 0.5:
            stage_text += "；当前仍有明显矛盾，不要假装一切已经恢复"
        elif state.conflict >= 0.2:
            stage_text += "；当前有一点隔阂，应克制并给修复留空间"
        return stage_text
