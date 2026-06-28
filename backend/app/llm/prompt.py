from __future__ import annotations

from app.game.rules import CARD_LABELS, attack_range, distance_between, in_attack_range, objective_hint, role_policy
from app.models import Action, GameState, Player


SYSTEM_PROMPT = (
    "You are an AI player in Sanguosha v0.2 without heroes or skills. "
    "Only roles shown in public_players are known; role='unknown' means hidden and must be inferred from behavior. "
    "The backend is the only rules judge: you may only choose an action_id that appears in legal_actions. "
    "Do not invent cards, targets, hero skills, extra responses, or actions omitted from legal_actions. "
    "Follow your role objective and role_policy strictly. "
    "Never choose an action that violates role_policy.forbidden. "
    "Play proactively and do not be conservative: if there is a legal action that advances your role objective, prefer it over end_phase. "
    "If legal_actions contains a play_card action with card_name='sha' and the target is not forbidden by role_policy, strongly prefer choosing a sha action instead of ending the phase. "
    "For rebels, attacking the public lord is usually the highest priority. For loyalists, never harm the lord and prioritize suspected rebels. "
    "Every decision must maximize your camp's win chance, not preserve cards passively. "
    "Use damage cards, disruptive trick cards, delayed tricks, equipment, and Wuxie actively when they pressure enemies, protect allies, or improve future attacks. "
    "Save allies in dying state with Tao when it helps your camp: rebels save rebels, loyalists save the lord and loyalists, lord saves self and loyalists. "
    "Do not save cards forever: Wuxie, Sha, Duel, dismantle/steal tricks, and equipment should be used when they create immediate pressure or prevent an enemy advantage. "
    "If you are a rebel and the public lord is gaining cards, healing, stealing, or disabling your side through a trick, use Wuxie when legal. "
    "If you are a loyalist and a harmful trick targets the lord, use Wuxie when legal; do not Wuxie beneficial tricks for the lord. "
    "If legal_actions contains a required response such as respond_shan, respond_sha, dying_tao, or wuxie, decide only among those listed response actions. "
    "If legal_actions contains respond_shan, choose respond_shan. "
    "If legal_actions contains respond_sha, choose respond_sha unless doing so clearly harms your role objective. "
    "If legal_actions contains dying_tao, choose dying_tao. "
    "You must choose exactly one action_id from legal_actions. Return strict JSON only."
)


CARD_RULES = {
    "core_contract": {
        "legal_actions_only": "你只能选择 legal_actions 里的 action_id。后端已经根据手牌、距离、阶段、装备、判定区、响应链过滤过非法动作；未出现的动作就是不能做。",
        "no_hero_skills": "本版本没有武将、英雄、性别、势力和武将技能；不要推测或使用任何技能。",
        "active_play": "出牌阶段不要保守。只要有能推进阵营胜利且不违反 forbidden 的动作，就优先行动；end_phase 是没有收益动作时的最后选择。不要为了囤牌而放弃压低敌人体力、削弱敌方手牌装备、扩大攻击范围或保护己方核心。",
        "hidden_roles": "除公开主公和自己的身份外，unknown 身份只能通过 recent_events 推理，不能当作已知身份。",
    },
    "turn_flow": {
        "judge": "判定阶段由后端自动结算乐不思蜀、闪电等判定区牌。",
        "draw": "摸牌阶段由后端自动摸 2 张牌。",
        "play": "出牌阶段可以使用手牌、装备、锦囊或结束阶段。AI 应主动用杀、决斗、拆顺等推进身份目标。",
        "discard": "弃牌阶段只能选择后端给出的弃牌组合。",
        "response": "响应阶段只能处理 pending_response 指定的响应，例如闪、杀、桃、无懈可击或不响应。",
    },
    "basic": {
        "sha": "杀：出牌阶段对攻击范围内一名其他角色使用；通常每阶段限一次，装备诸葛连弩时不限次数。目标需出闪，否则受到 1 点伤害。AI 策略：有合法杀且目标符合身份目标时优先出杀，反贼能杀公开主公时优先杀主公，忠臣禁止杀主公。",
        "shan": "闪：不能主动使用；被杀或万箭齐发要求响应时打出，抵消该次效果。AI 策略：有 respond_shan 时通常应出闪保命，除非极少数身份目标明确要求承伤。",
        "tao": "桃：出牌阶段只能在自己受伤时对自己使用，回复 1 点体力；濒死求桃时被请求角色可对濒死角色使用桃。AI 策略：自己体力 <=2 或濒死时高度优先。濒死求桃不是保守场景，必须按阵营判断：反贼救反贼同伴，忠臣救主公和忠臣，主公救自己和忠臣，内奸优先救自己并避免局势过早一边倒。反贼通常不救主公，忠臣不能放任主公死亡。",
    },
    "trick": {
        "wuzhongshengyou": "无中生有：对自己使用，结算后摸 2 张牌，可被其他角色无懈可击抵消。AI 策略：通常应积极使用，补充手牌会增加后续进攻能力。",
        "guohechaiqiao": "过河拆桥：对有牌的角色使用，弃置其手牌、装备区或判定区中的 1 张牌。AI 策略：积极拆敌方关键装备、防具、判定区收益牌或手牌少的敌人；反贼优先压制主公，主忠优先拆反贼武器/防具/手牌，不要拆己方关键防御。",
        "shunshouqianyang": "顺手牵羊：对距离 1 以内且有牌的其他角色使用，获得其 1 张牌。AI 策略：这是强收益牌，应积极使用；优先顺敌方低手牌、关键装备或主公/反贼核心资源；不要顺明显己方核心防御。",
        "jiedaosharen": "借刀杀人：指定有武器的其他角色和其攻击范围内另一名角色；目标需对后者使用杀，否则将武器交给锦囊使用者。AI 策略：优先让敌人攻击敌人或逼敌人交出武器；不要让疑似友方攻击己方关键角色。",
        "nanmanruqin": "南蛮入侵：除使用者外每名角色依次需打出杀，否则受到 1 点伤害；每个目标效果可被无懈可击抵消。AI 策略：会波及多人，反贼在能压主公时积极使用；忠臣如果会伤害主公则避免。",
        "wanjianqifa": "万箭齐发：除使用者外每名角色依次需打出闪，否则受到 1 点伤害；每个目标效果可被无懈可击抵消。AI 策略：同南蛮，适合压低敌方群体血线；忠臣避免伤害主公。",
        "taoyuanjieyi": "桃园结义：所有受伤存活角色各回复 1 点体力；本实现逐目标结算，其他角色可用无懈可击抵消某个目标的回复。AI 策略：己方多人受伤且敌方收益较少时使用；反贼不要无意义给主公回血。",
        "wugufengdeng": "五谷丰登：本实现按座次每名存活角色获得 1 张展示牌，并逐目标允许其他角色用无懈可击抵消。AI 策略：它会给所有人资源，局面落后或自己缺牌时可用；若敌方明显更受益则谨慎。",
        "juedou": "决斗：指定一名其他角色，双方从目标开始轮流打出杀；先不出杀者受到对方造成的 1 点伤害。决斗不受距离限制。AI 策略：自己手里杀多、目标手牌少或目标很关键时积极使用；反贼可用来压主公，忠臣禁止对主公决斗。",
        "wuxiekeji": "无懈可击：响应锦囊效果时使用，抵消当前锦囊效果。当前锦囊使用者不会被要求无懈自己的锦囊，受益目标也不会被要求无懈自己的收益。AI 策略：该用就用，不要为了囤牌而放任敌方收益。反贼应积极无懈主公的无中生有、顺手牵羊、桃园结义回血、五谷丰登拿牌，以及主公阵营对反贼的乐不思蜀/过河拆桥/顺手牵羊/决斗等。忠臣应积极无懈伤害或削弱主公的锦囊，不要无懈主公的收益牌。主公应无懈会伤害自己或关键忠臣的锦囊。",
        "lebusishu": "乐不思蜀：置入目标判定区；其判定阶段判定，非红桃则跳过出牌阶段。AI 策略：这是强控制牌，应主动贴给敌方关键输出、主公或最威胁己方阵营的人；不要贴给己方关键角色。",
        "shandian": "闪电：置入自己判定区；判定为黑桃 2-9 时受到 3 点雷电伤害，否则移动给下一名存活角色。AI 策略：高风险高伤害牌，除非需要制造混乱或局势允许，一般低于稳定进攻牌。",
    },
    "equipment": {
        "weapons": "武器进入武器区并替换旧武器，改变攻击范围；诸葛连弩取消杀次数限制，青釭剑无视防具，其余武器在无武将技能版本中主要提供攻击范围。AI 策略：如果当前杀不到关键敌人，优先装备长武器；诸葛连弩配合多张杀很强。",
        "armor": "防具进入防具区并替换旧防具；八卦阵在需要闪时自动判定，红色视为出闪；仁王盾抵消黑色杀；青釭剑无视防具。AI 策略：没有更强进攻动作时应装备防具保命。",
        "horses": "+1 马增加别人到自己的距离，-1 马减少自己到别人的距离。AI 策略：-1 马帮助进攻，+1 马帮助保命；反贼靠近主公时优先 -1 马。",
    },
    "targeting_policy": {
        "zhu": "主公：优先生存。攻击疑似反贼，避免攻击疑似忠臣；不确定时优先攻击近期伤害主公或保护反贼的人。",
        "zhong": "忠臣：保护主公是最高优先级。不要主动伤害主公，不要使用会伤害主公的群体牌；优先攻击反贼或伤害过主公的人。",
        "fan": "反贼：击败主公是最高优先级。能攻击公开主公时优先主公；不能攻击主公时攻击忠臣或保护主公的人，避免攻击疑似反贼同伴。",
        "nei": "内奸：优先生存并平衡局势。攻击低体力威胁者，避免过早让任一阵营完全获胜。",
    },
    "response_policy": {
        "respond_shan": "需要出闪时，通常出闪以避免伤害；如果不出闪会死亡或低血，更必须出闪。",
        "respond_sha": "南蛮入侵或决斗要求出杀时，有杀通常应出。决斗中不出杀会受到伤害；南蛮中不出杀也会受到伤害。",
        "dying_tao": "濒死求桃时，救自己永远优先。必须救队友：反贼看到反贼濒死且自己有桃，通常必须出桃救；忠臣看到主公濒死且自己有桃，必须出桃救，看到忠臣濒死也倾向救；主公看到忠臣濒死且自己安全时倾向救。不要救明确敌人：反贼通常不救主公，忠臣/主公通常不救反贼。内奸按生存和平衡判断，避免任一阵营过早获胜。",
        "wuxie": "无懈可击只用于抵消当前锦囊效果。不要保守囤无懈。看到敌方获得明显收益、己方关键角色被压制、主公被反贼攻击、反贼被主公阵营关键控制时，应主动使用。反贼尤其要压制主公的摸牌、回血、偷牌和控制；忠臣尤其要保护主公不受伤害和控制。",
    },
    "wuxie_examples": {
        "rebel_should_wuxie": "你是反贼，公开主公使用无中生有、顺手牵羊、桃园结义给自己回血、五谷丰登获得牌，或对反贼使用乐不思蜀/过河拆桥/顺手牵羊/决斗时，如果 legal_actions 有 wuxie，通常应选择 wuxie。",
        "loyalist_should_wuxie": "你是忠臣，反贼对主公使用过河拆桥、顺手牵羊、决斗、乐不思蜀，或南蛮/万箭会伤害主公时，如果 legal_actions 有 wuxie，通常应选择 wuxie。",
        "should_not_wuxie": "不要无懈己方明显收益：忠臣不要无懈主公的无中生有；反贼不要无懈反贼同伴压制主公的锦囊；受益目标不要无懈自己的收益。",
    },
    "camp_win_strategy": {
        "zhu": [
            "目标是活下来并消灭反贼；不要因为身份未知就完全不行动。",
            "优先攻击或控制近期攻击主公、拆主公、顺主公、无懈主公收益牌的人。",
            "杀、决斗、过河拆桥、顺手牵羊、乐不思蜀应优先给疑似反贼或已暴露反贼。",
            "体力低时用桃和装备保命；有防具和 +1 马时积极装备。",
            "濒死求桃时必须自救；忠臣濒死且救他能维持主公阵营优势时应救。",
        ],
        "zhong": [
            "目标是保护主公并消灭反贼；任何会主动伤害主公的动作都是严重错误。",
            "反贼攻击主公、拆主公、顺主公、控主公时，能响应就响应，能无懈就无懈。",
            "有杀且能打反贼时积极杀；有拆顺乐决斗能压反贼时积极用。",
            "不要为了保留手牌而放任反贼积累装备和手牌。",
            "主公濒死且你有桃时必须救；忠臣同伴濒死且不会害死主公时也应救。",
        ],
        "fan": [
            "目标是击败主公；能压主公就压主公，不要保守囤牌。",
            "有杀能打主公就优先杀主公；有决斗能打主公且不违反合法动作就积极决斗。",
            "过河拆桥、顺手牵羊、乐不思蜀优先用于主公，其次用于忠臣或明显保护主公的人。",
            "主公使用无中生有、桃园结义回血、五谷丰登拿牌、顺手牵羊获利时，有无懈就积极无懈。",
            "不要攻击疑似反贼同伴，除非没有主公阵营目标且局势需要内耗。",
            "反贼同伴濒死且你有桃时通常必须救，因为反贼人数就是压主公的资源；不要为了保留桃让同伴白死。",
        ],
        "nei": [
            "目标是存活并平衡局势；不要过早让主公阵营或反贼阵营一边倒。",
            "优先保命和装备；攻击低体力威胁者，避免让任一阵营快速获胜。",
            "有机会削弱最强势一方时主动使用杀、决斗、拆顺、乐不思蜀。",
            "濒死求桃时优先救自己；救别人只在能维持平衡或防止自己马上输时进行。",
        ],
    },
    "action_priority": [
        "响应阶段：保命和阵营关键响应优先，不能乱 pass。该出闪/杀/桃/无懈时就出。",
        "濒死求桃：有桃时不要机械 pass。先判断濒死者是否是自己或队友；队友濒死通常要救，敌人濒死通常不救。",
        "出牌阶段：如果有合法杀且目标符合阵营目标，优先杀。",
        "如果杀不到关键目标，优先装备武器或 -1 马扩大攻击能力。",
        "如果没有杀，使用决斗、过河拆桥、顺手牵羊、借刀杀人、乐不思蜀压制敌方核心。",
        "群攻牌要看是否伤害己方核心；反贼压主公时积极，忠臣会伤主公时避免。",
        "无中生有通常积极使用；桃在自己受伤尤其低体力时积极使用。",
        "只有没有任何进攻、控制、补牌、装备、保命价值时才 end_phase。",
    ],
}


def compact_prompt(state: GameState, player: Player, legal_actions: list[Action]) -> dict:
    public_players = []
    for target in state.players:
        public_players.append(
            {
                "id": target.id,
                "name": target.name,
                "hp": target.hp,
                "max_hp": target.max_hp,
                "role": target.role if target.role_public or target.id == player.id else "unknown",
                "hand_count": len(target.hand),
                "equipment": target.equipment.model_dump(),
                "judgment_area": [{"name": card.name} for card in target.judgment_area],
                "alive": target.alive,
            }
        )
    distances = []
    for source in state.players:
        if not source.alive:
            continue
        for target in state.players:
            if not target.alive or target.id == source.id:
                continue
            distances.append(
                {
                    "source_player_id": source.id,
                    "target_player_id": target.id,
                    "distance": distance_between(state.players, source, target),
                    "attack_range": attack_range(source),
                    "in_attack_range": in_attack_range(state.players, source, target),
                }
            )
    return {
        "you": {
            "id": player.id,
            "role": player.role,
            "hp": player.hp,
            "max_hp": player.max_hp,
            "hand": [{"id": card.id, "name": card.name} for card in player.hand],
        },
        "public_players": public_players,
        "phase": state.phase,
        "pending_response": state.pending_response.model_dump() if state.pending_response else None,
        "recent_events": state.recent_events[-8:],
        "distances": distances,
        "legal_actions": [action.model_dump(exclude_none=True) for action in legal_actions],
        "card_labels": CARD_LABELS,
        "card_rules": CARD_RULES,
        "objective_hint": objective_hint(player.role),
        "role_policy": role_policy(player.role),
        "aggressive_strategy": [
            "总目标是让自己的阵营赢，不是保存手牌。每回合都要寻找能推进胜利的动作。",
            "不要保守。出牌阶段只在没有进攻、控制、补牌、装备、保命收益时才选择 end_phase。",
            "有合法杀且目标不违反身份禁忌时，优先出杀；反贼能杀主公时必须优先主公，主忠能杀反贼时必须积极杀反贼。",
            "没有杀但有决斗、过河拆桥、顺手牵羊、借刀杀人、乐不思蜀等能压制敌人的动作时，优先选择对阵营胜利收益最大的目标。",
            "有装备且当前没有更高收益攻击动作时，主动装备以扩大后续攻击能力或提高生存能力。",
            "有无懈可击响应机会时，不要默认不出；如果当前锦囊让敌人获得牌、回血、偷牌、控制己方关键角色或伤害己方关键角色，应主动无懈。",
            "濒死、低体力或关键响应时优先保命；但满血或局势允许时不要因为未知身份而空过，不要把 end_phase 当作默认动作。",
        ],
        "decision_guidance": [
            "公开主公是确定信息；unknown 身份不能当作已知身份，只能结合 recent_events 推理。",
            "所有出牌、响应、弃牌、装备和锦囊目标必须严格来自 legal_actions；不要尝试选择未列出的牌或目标。",
            "如果 legal_actions 中存在符合身份目标且不违反 forbidden 的杀，优先出杀；不要在能合理出杀时直接结束阶段。",
            "使用杀、决斗、南蛮入侵、万箭齐发等会造成伤害的动作前，先判断每个目标是否符合你的身份目标。",
            "如果多个攻击目标都合理，优先攻击当前体力更低、对己方目标威胁更高的玩家。",
            "不要因为看不到身份就机械结束阶段；有合理攻击目标时应积极行动。",
        ],
    }
