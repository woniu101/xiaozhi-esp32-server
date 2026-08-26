import json


def is_character_style_active(character_style) -> bool:
    return isinstance(character_style, dict) and character_style.get("active") is True


def resolve_runtime_prompt(role_prompt, character_style):
    """Choose exactly one runtime identity while preserving role_prompt in storage."""
    if not is_character_style_active(character_style):
        return role_prompt
    resolved_prompt = character_style.get("resolved_prompt")
    if not isinstance(resolved_prompt, str) or not resolved_prompt.strip():
        raise ValueError("已绑定的人物风格缺少 resolved_prompt")
    return resolved_prompt + build_signature_audio_contract(character_style)


def build_signature_audio_contract(character_style) -> str:
    """Pin only the recorded surface text; the Skill still owns semantic timing."""
    if not is_character_style_active(character_style):
        return ""
    config = character_style.get("signature_config")
    if not isinstance(config, dict) or config.get("enabled") is not True:
        return ""
    raw_items = config.get("items")
    if not isinstance(raw_items, list):
        return ""

    canonical = []
    for item in raw_items[:50]:
        if not isinstance(item, dict) or item.get("enabled") is not True:
            continue
        item_id = item.get("id")
        display_text = item.get("display_text")
        audio_path = item.get("audio_path")
        if not all(isinstance(value, str) and value for value in (item_id, display_text, audio_path)):
            continue
        canonical.append((item_id, display_text))
    if not canonical:
        return ""

    lines = [
        "",
        "<signature_audio_contract>",
        "固定录音只改变播放来源，不改变人物何时使用招牌表达。只有当人物 Skill 和当前对话上下文本来就决定使用某条表达时，才原样输出下面对应的规范台词；录音可用本身不得提高使用频率。",
    ]
    lines.extend(
        f"- {item_id}: {json.dumps(text, ensure_ascii=False)}"
        for item_id, text in canonical
    )
    lines.append("</signature_audio_contract>")
    return "\n" + "\n".join(lines)
