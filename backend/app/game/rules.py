from __future__ import annotations

ROLE_SETS = {
    2: ["zhu", "fan"],
    3: ["zhu", "fan", "fan"],
    4: ["zhu", "zhong", "fan", "fan"],
    5: ["zhu", "zhong", "fan", "fan", "nei"],
    6: ["zhu", "zhong", "fan", "fan", "fan", "nei"],
}


ROLE_LABELS = {
    "zhu": "主公",
    "zhong": "忠臣",
    "fan": "反贼",
    "nei": "内奸",
    "unknown": "未知",
}


CARD_LABELS = {
    "sha": "杀",
    "shan": "闪",
    "tao": "桃",
}


def objective_hint(role: str) -> str:
    if role == "zhu":
        return "你是主公。优先生存，并击败所有反贼。"
    if role == "zhong":
        return "你是忠臣。保护主公，并帮助主公阵营击败反贼。"
    if role == "fan":
        return "你是反贼。优先击败主公。"
    return "你是内奸。v0.1 中内奸胜利条件未完整实现，先尽量生存并影响局势。"

