from __future__ import annotations

import re


CONCEPT_PATTERNS = {
    "identity": r"名字|叫什|称呼|怎么叫|是谁",
    "preference": r"喜欢|不喜欢|偏好|爱好|口味|想吃|想喝",
    "work": r"工作|上班|加班|公司|同事|老板|项目|面试|裁员|下班",
    "study": r"学习|上课|考试|作业|论文|学校|老师|成绩",
    "sleep": r"睡觉|失眠|熬夜|困|休息|起床|做梦",
    "emotion": r"开心|难过|伤心|焦虑|生气|委屈|害怕|压力|心情|累",
    "relationship": r"朋友|家人|对象|恋爱|分手|吵架|道歉|关系",
    "health": r"身体|生病|不舒服|医院|吃药|头疼|发烧",
    "food": r"吃饭|早餐|午饭|晚饭|咖啡|奶茶|饮料|菜|饿",
    "plan": r"计划|准备|打算|明天|后天|今晚|周末|下周|到时候|提醒|约定",
    "result": r"结果|完成|做完|结束|搞定|通过|失败|取消|没去成",
}


def semantic_tokens(value: str) -> set[str]:
    """Return bounded lexical tokens suitable for Chinese short-text matching."""
    text = re.sub(r"\s+", "", str(value or "").lower())[:1000]
    tokens: set[str] = set()
    for token in re.findall(r"[a-z0-9_]{2,}|[\u4e00-\u9fff]{2,}", text):
        if re.fullmatch(r"[\u4e00-\u9fff]+", token):
            tokens.update(token[index:index + 2] for index in range(len(token) - 1))
            if len(token) <= 8:
                tokens.add(token)
        else:
            tokens.add(token)
    return tokens


def semantic_concepts(value: str) -> set[str]:
    text = str(value or "").lower()
    return {name for name, pattern in CONCEPT_PATTERNS.items() if re.search(pattern, text)}


def semantic_overlap(left: str, right: str) -> float:
    left_tokens = semantic_tokens(left)
    right_tokens = semantic_tokens(right)
    lexical = len(left_tokens & right_tokens)
    concepts = len(semantic_concepts(left) & semantic_concepts(right))
    return lexical + concepts * 2.5
