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
    "wuzhongshengyou": "无中生有",
    "guohechaiqiao": "过河拆桥",
    "shunshouqianyang": "顺手牵羊",
    "jiedaosharen": "借刀杀人",
    "nanmanruqin": "南蛮入侵",
    "wanjianqifa": "万箭齐发",
    "taoyuanjieyi": "桃园结义",
    "wugufengdeng": "五谷丰登",
    "juedou": "决斗",
    "wuxiekeji": "无懈可击",
    "lebusishu": "乐不思蜀",
    "shandian": "闪电",
    "zhugeliannu": "诸葛连弩",
    "qinggangjian": "青釭剑",
    "cixiongshuanggujian": "雌雄双股剑",
    "hanbingjian": "寒冰剑",
    "qinglongyanyuedao": "青龙偃月刀",
    "zhangbashemao": "丈八蛇矛",
    "guanshifu": "贯石斧",
    "fangtianhuaji": "方天画戟",
    "qilingong": "麒麟弓",
    "baguazhen": "八卦阵",
    "renwangdun": "仁王盾",
    "jueying": "绝影",
    "dilu": "的卢",
    "zhuahuangfeidian": "爪黄飞电",
    "dawan": "大宛",
    "chitu": "赤兔",
    "zixing": "紫骍",
}

TRICK_CARDS = {
    "wuzhongshengyou",
    "guohechaiqiao",
    "shunshouqianyang",
    "jiedaosharen",
    "nanmanruqin",
    "wanjianqifa",
    "taoyuanjieyi",
    "wugufengdeng",
    "juedou",
    "lebusishu",
    "shandian",
}

WEAPON_RANGES = {
    "zhugeliannu": 1,
    "qinggangjian": 2,
    "cixiongshuanggujian": 2,
    "hanbingjian": 2,
    "qinglongyanyuedao": 3,
    "zhangbashemao": 3,
    "guanshifu": 3,
    "fangtianhuaji": 4,
    "qilingong": 5,
}

ARMOR_CARDS = {"baguazhen", "renwangdun"}
ATTACK_HORSES = {"dawan", "chitu", "zixing"}
DEFENSE_HORSES = {"jueying", "dilu", "zhuahuangfeidian"}
EQUIPMENT_CARDS = set(WEAPON_RANGES) | ARMOR_CARDS | ATTACK_HORSES | DEFENSE_HORSES
DELAYED_TRICKS = {"lebusishu", "shandian"}
RED_SUITS = {"heart", "diamond"}
BLACK_SUITS = {"spade", "club"}


def attack_range(player) -> int:
    if player.equipment.weapon:
        return WEAPON_RANGES[player.equipment.weapon.name]
    return 1


def distance_between(players: list, source, target) -> int:
    alive = [player for player in players if player.alive]
    if source not in alive or target not in alive or source.id == target.id:
        return 0
    source_index = alive.index(source)
    target_index = alive.index(target)
    seat_distance = min((target_index - source_index) % len(alive), (source_index - target_index) % len(alive))
    distance = max(1, seat_distance)
    if source.equipment.attack_horse:
        distance -= 1
    if target.equipment.defense_horse:
        distance += 1
    return max(1, distance)


def in_attack_range(players: list, source, target) -> bool:
    return distance_between(players, source, target) <= attack_range(source)


def objective_hint(role: str) -> str:
    if role == "zhu":
        return "你是主公。优先生存，根据公开信息和行为推理谁更像反贼，优先攻击疑似反贼，避免攻击疑似忠臣。"
    if role == "zhong":
        return "你是忠臣。保护主公是最高优先级，绝不能主动对主公使用杀或造成伤害；优先攻击反贼。"
    if role == "fan":
        return "你是反贼。优先击败主公，根据行为推理谁更像反贼同伴，避免攻击疑似同伴。"
    return "你是内奸。v0.2 中内奸胜利条件仍未完整实现，先尽量生存并影响局势，避免过早帮助任一阵营获胜。"


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
