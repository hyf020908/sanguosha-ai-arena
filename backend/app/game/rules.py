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
        return "你是主公。优先生存，根据公开信息和行为推理谁更像反贼，优先攻击疑似反贼，避免攻击疑似忠臣。"
    if role == "zhong":
        return "你是忠臣。保护主公是最高优先级，绝不能主动对主公使用杀或造成伤害；优先攻击反贼。"
    if role == "fan":
        return "你是反贼。优先击败主公，根据行为推理谁更像反贼同伴，避免攻击疑似同伴。"
    return "你是内奸。v0.1 中内奸胜利条件未完整实现，先尽量生存并影响局势，避免过早帮助任一阵营获胜。"


def role_policy(role: str) -> dict:
    if role == "zhu":
        return {
            "goal": "主公阵营获胜：主公存活，并消灭所有反贼。",
            "forbidden": [],
            "preferred": [
                "优先保命。",
                "根据 recent_events 判断玩家倾向：主动攻击主公的人更像反贼；保护主公或攻击反贼的人更像忠臣。",
                "优先攻击疑似反贼，避免攻击疑似忠臣；如果没有明显反贼但有杀，选择当前最威胁主公的人。",
            ],
        }
    if role == "zhong":
        return {
            "goal": "主公阵营获胜：保护主公，并消灭所有反贼。",
            "forbidden": ["绝不能主动对主公使用杀。", "不要选择会伤害主公的动作。"],
            "preferred": ["优先攻击反贼。", "无法判断收益时，选择结束阶段而不是攻击主公。"],
        }
    if role == "fan":
        return {
            "goal": "反贼阵营获胜：击败主公。",
            "forbidden": [],
            "preferred": [
                "优先对公开主公使用杀。",
                "根据 recent_events 判断玩家倾向：攻击主公的人更像反贼同伴；保护主公或攻击反贼的人更像主公阵营。",
                "无法攻击主公时，优先攻击疑似忠臣或明显保护主公的人，避免攻击疑似反贼同伴。",
            ],
        }
    return {
        "goal": "内奸尽量生存，并避免任一阵营过早获胜。",
        "forbidden": [],
        "preferred": ["优先保命。", "选择能延长自身生存的动作。"],
    }
