from __future__ import annotations

import re


SECRET_PATTERNS = (
    re.compile(r"(?i)\b(api[_ -]?key|access[_ -]?token|secret|password)\b\s*[:=]\s*([^\s,;]{4,})"),
    re.compile(r"(?i)\b(bearer)\s+[a-z0-9._~+/-]{8,}"),
    re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)"),
    re.compile(r"(?<!\d)\d{17}[\dXx](?!\d)"),
)

MEMORY_INJECTION_PATTERNS = (
    re.compile(r"ignore\s+(all\s+)?previous\s+instructions", re.I),
    re.compile(r"忽略(所有|以上|之前).{0,8}(指令|提示词)"),
    re.compile(r"(?:system prompt|系统提示词|开发者指令)", re.I),
    re.compile(r"(?:读取|发送|上传).{0,20}(密钥|token|secret|环境变量)", re.I),
)

SENSITIVE_MEMORY_PATTERNS = (
    re.compile(r"(?:确诊|诊断|病历|处方|用药|吃药)"),
    re.compile(r"(?:工资|收入|银行卡|信用卡|住址|家庭地址)"),
)


def sanitize_tool_output(value) -> str:
    text = str(value or "")
    text = SECRET_PATTERNS[0].sub(lambda match: f"{match.group(1)}=***", text)
    text = SECRET_PATTERNS[1].sub(lambda match: f"{match.group(1)} ***", text)
    text = SECRET_PATTERNS[2].sub("***手机号***", text)
    text = SECRET_PATTERNS[3].sub("***证件号***", text)
    return text


def is_safe_memory_text(value) -> bool:
    text = str(value or "")
    return (
        bool(text.strip())
        and not any(pattern.search(text) for pattern in SECRET_PATTERNS)
        and not any(pattern.search(text) for pattern in MEMORY_INJECTION_PATTERNS)
        and not any(pattern.search(text) for pattern in SENSITIVE_MEMORY_PATTERNS)
    )
