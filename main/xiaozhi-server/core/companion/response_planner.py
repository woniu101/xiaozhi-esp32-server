from __future__ import annotations

from dataclasses import asdict, dataclass
import re
from typing import Any

from .semantic_text import semantic_concepts
from .state_models import CompanionEvent, CompanionState


@dataclass(frozen=True)
class ResponsePlan:
    dialogue_act: str
    emotional_tone: str
    response_length: str
    question_policy: str
    initiative: str
    memory_policy: str
    scene_tags: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["scene_tags"] = list(self.scene_tags)
        return value

    def render(self) -> str:
        acts = {
            "comfort": "先接住情绪，再回应具体事情；不要立刻讲大道理",
            "boundary": "保持人物边界，短而克制，不讨好也不升级冲突",
            "repair": "接受或推动修复，不假装矛盾从未发生",
            "receive": "自然接住对方的感谢或关心，不展开客服式客套",
            "co_create": "参与共同计划，明确一个自然的下一步",
            "advise": "先给可执行结论，再补最必要的理由",
            "answer": "直接回答问题，不复述题目",
            "act": "优先完成动作或确认必要参数，少解释",
            "banter": "轻松接话，可以调侃，但不要强行制造笑点",
            "recall": "自然使用相关记忆作答，不说‘根据记忆库’",
            "listen": "以倾听和回应为主，不抢着解决问题",
            "engage": "像熟人聊天一样接住重点，不做总结报告",
        }
        lengths = {"short": "优先 1—3 句", "medium": "优先 3—5 句", "long": "仅在确有必要时展开"}
        questions = {
            "none": "本轮不要用问题强行延续对话",
            "optional": "只有确实有帮助时才问一个问题",
            "one": "最多问一个具体、自然的问题",
        }
        memory = {
            "none": "不要主动提旧事",
            "optional": "相关记忆能让回应更自然时最多使用一条",
            "use_one": "使用一条最相关记忆，但不要逐条盘点",
        }
        return (
            "<response_plan>\n"
            f"回应动作：{acts.get(self.dialogue_act, acts['engage'])}。\n"
            f"语气：{self.emotional_tone}；篇幅：{lengths.get(self.response_length, lengths['short'])}。\n"
            f"提问：{questions.get(self.question_policy, questions['optional'])}。\n"
            f"记忆：{memory.get(self.memory_policy, memory['none'])}。\n"
            "避免使用‘作为AI’‘我理解你的感受’‘还有什么可以帮你’等通用助手套话；"
            "除非用户明确要求，不使用标题、列表或总结式结构。\n"
            "该计划只约束表达方式，不要在回答中复述计划内容。\n"
            "</response_plan>"
        )


class ResponsePlanner:
    def plan(
        self,
        user_message: str,
        state: CompanionState,
        events: list[CompanionEvent] | None = None,
        memories: list[dict] | None = None,
    ) -> ResponsePlan:
        text = str(user_message or "").strip()
        event_types = {event.event_type for event in (events or [])}
        concepts = semantic_concepts(text)
        explicit_recall = bool(re.search(r"还?记得|我之前说|上次|你知道我", text))

        if "user_insulted_companion" in event_types:
            act, tone, length, question = "boundary", "克制、略冷", "short", "none"
        elif "user_apologized" in event_types:
            act, tone, length, question = "repair", "克制但留有修复空间", "short", "none"
        elif "user_expressed_joy" in event_types:
            act, tone, length, question = "receive", "真诚地一起高兴，但不夸张", "short", "optional"
        elif {"user_expressed_exhaustion", "user_expressed_distress"} & event_types:
            act, tone, length, question = "comfort", "具体、温和、不夸张", "short", "optional"
        elif "meaningful_disclosure" in event_types:
            act, tone, length, question = "listen", "认真、给空间", "medium", "one"
        elif "user_expressed_gratitude" in event_types or "user_showed_care" in event_types:
            act, tone, length, question = "receive", "自然、带一点温度", "short", "none"
        elif explicit_recall:
            act, tone, length, question = "recall", "熟悉、自然", "short", "none"
        elif "shared_plan_created" in event_types or re.search(r"(?:我|我们).{0,10}(?:准备|打算|计划|想要).+", text):
            act, tone, length, question = "co_create", "有参与感但不施压", "short", "optional"
        elif re.search(r"怎么办|怎么选|该不该|建议|帮我分析", text):
            act, tone, length, question = "advise", "直接但不说教", "medium", "optional"
        elif re.search(r"[?？]|什么|为什么|怎么|多少|哪(?:个|里)", text):
            act, tone, length, question = "answer", "自然、直接", "medium", "none"
        elif re.search(r"^(打开|关闭|播放|暂停|设置|调高|调低|查|搜|提醒)", text):
            act, tone, length, question = "act", "利落", "short", "none"
        elif re.search(r"^(你好|嗨|哈喽|在吗|早|晚安)|哈哈|笑死", text):
            act, tone, length, question = "banter", "轻松、有反应", "short", "optional"
        else:
            act, tone, length, question = "engage", "口语化、自然", "short", "optional"

        if state.emotion.irritation >= 0.3 and act not in {"repair", "boundary"}:
            tone = "略有保留、不过分热情"
        memory_policy = "none"
        if memories:
            memory_policy = "use_one" if explicit_recall else "optional"
        tags = tuple(dict.fromkeys((act, *sorted(concepts))))
        return ResponsePlan(
            dialogue_act=act,
            emotional_tone=tone,
            response_length=length,
            question_policy=question,
            initiative="low" if question == "none" else "medium",
            memory_policy=memory_policy,
            scene_tags=tags,
        )


def is_explicit_recall_request(user_message: str) -> bool:
    return bool(re.search(r"还?记得|我之前说|上次|你知道我", str(user_message or "")))
