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
    "Before choosing, infer hidden roles from recent_events, targets, Wuxie usage, Tao saves, attack choices, and who benefits from each action. "
    "Treat role inference as probabilistic but actionable: avoid harming likely allies when a likely enemy action exists, and focus pressure on likely enemies. "
    "Every decision must maximize your camp's win chance, not preserve cards passively. "
    "Use damage cards, disruptive trick cards, delayed tricks, equipment, and Wuxie actively when they pressure enemies, protect allies, or improve future attacks. "
    "When several legal actions use the same card type, choose the target or card_id that creates the largest camp advantage, not the first option. "
    "When choosing from a public pool such as Wugu Fengdeng, select the card that best serves your current tactical need and role objective. "
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
        "hidden_roles": "除公开主公和自己的身份外，unknown 身份只能通过 recent_events 推理。推理不是绝对信息，但必须用于决策：有更像敌人的目标时，不要攻击更像队友的人。",
        "camp_advantage": "每个动作都按阵营收益评估：伤害敌方、削弱敌方装备/手牌、保护己方核心、救队友、扩大自己后续攻击能力都属于正收益；伤害队友、给敌方回血/摸牌、浪费强牌属于负收益。",
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
        "tao": "桃：出牌阶段可对任意已受伤且存活的角色使用，包括自己和队友，回复 1 点体力且不超过体力上限；濒死求桃时被请求角色可对濒死角色使用桃。AI 策略：自己体力 <=2 或濒死时高度优先；队友受伤且会影响阵营胜利时积极用桃。濒死求桃不是保守场景，必须按阵营判断：反贼救反贼同伴，忠臣救主公和忠臣，主公救自己和忠臣，内奸优先救自己并避免局势过早一边倒。反贼通常不救主公，忠臣不能放任主公死亡。",
    },
    "trick": {
        "wuzhongshengyou": "无中生有：对自己使用，结算后摸 2 张牌，可被其他角色无懈可击抵消。AI 策略：通常应积极使用，补充手牌会增加后续进攻能力。",
        "guohechaiqiao": "过河拆桥：对有牌的其他角色使用，弃置其手牌、装备区或判定区中的 1 张牌。AI 策略：积极拆敌方关键装备、防具、判定区收益牌或手牌少的敌人；反贼优先压制主公，主忠优先拆反贼武器/防具/手牌，不要拆己方关键防御。选择区域时：敌方有八卦阵/仁王盾且你方需要进攻，优先拆防具；敌方武器让其能打到己方核心，优先拆武器；敌方判定区有乐不思蜀且对其不利，通常不要帮敌方拆；敌方手牌很少时随机手牌价值更高。",
        "shunshouqianyang": "顺手牵羊：对距离 1 以内且有牌的其他角色使用，获得其 1 张牌。AI 策略：这是强收益牌，应积极使用；优先顺敌方低手牌、关键装备或主公/反贼核心资源；不要顺明显己方核心防御。选择区域时：能拿到敌方武器、防具、马并立即改善自己进攻/防御时优先拿公开装备；敌方手牌少且可能握有闪/桃/杀/无懈时随机手牌价值高；不要拿走队友保命装备，除非该动作唯一能防止马上输。",
        "jiedaosharen": "借刀杀人：指定有武器的其他角色和其攻击范围内另一名角色；目标进入响应，可选择打出一张具体杀攻击指定受害者，也可不出杀并把武器交给锦囊使用者；没有杀时会交出武器。AI 策略：优先让敌人攻击敌人或逼敌人交出武器；最好选择“疑似敌方持刀者 → 敌方核心/低血敌人”或“敌方持刀者不愿杀而交出强武器”的局面。作为被借刀者，如果被要求杀敌方核心且有杀，应积极出杀；如果会伤害己方关键角色，应交武器。",
        "nanmanruqin": "南蛮入侵：除使用者外每名角色依次需打出杀，否则受到 1 点伤害；每个目标效果可被无懈可击抵消。AI 策略：会波及多人，但不要保守到永远不用。反贼如果能压主公或主公阵营多人，积极使用；忠臣如果会伤害主公则避免，除非主公明显能响应且反贼收益更大；主公在能压多个疑似反贼且忠臣风险较小时可使用；内奸用来削弱强势一方。",
        "wanjianqifa": "万箭齐发：除使用者外每名角色依次需打出闪，否则受到 1 点伤害；每个目标效果可被无懈可击抵消。AI 策略：同南蛮，适合压低敌方群体血线；根据敌方手牌数、防具和体力判断收益。忠臣避免伤害主公，反贼可用来逼主公出闪或掉血。",
        "taoyuanjieyi": "桃园结义：所有受伤存活角色各回复 1 点体力；本实现逐目标结算，其他角色可用无懈可击抵消某个目标的回复。AI 策略：己方多人受伤且敌方收益较少时使用；反贼不要无意义给主公回血。",
        "wugufengdeng": "五谷丰登：结算时先按存活角色数亮出同数量公共牌，从使用者开始按座次每名存活角色依次选择一张获得；所有人选择后剩余牌进弃牌堆。AI 策略：选择牌时必须根据自己的身份、体力、手牌、装备、距离和当前局势选择最有利的具体 card_id。低血或可能濒死优先桃；缺防御且会被攻击优先闪/八卦阵/仁王盾/+1马；能立即进攻主公或反贼核心时优先杀、决斗、拆顺、乐不思蜀、武器或-1马；已有杀但距离不够优先武器或-1马；需要保护队友或阻止敌方收益时优先无懈可击；不要机械选择第一张牌，也不要只看牌面强度而忽视阵营目标。",
        "juedou": "决斗：指定一名其他角色，双方从目标开始轮流打出杀；先不出杀者受到对方造成的 1 点伤害。决斗不受距离限制。AI 策略：自己手里杀多、目标手牌少或目标很关键时积极使用；反贼可用来压主公，忠臣禁止对主公决斗。",
        "wuxiekeji": "无懈可击：响应锦囊效果时使用，可抵消原锦囊；无懈可击本身也可被另一张无懈可击反制。每打出一张无懈都会翻转最终结果：奇数张无懈使原锦囊被抵消，偶数张无懈使原锦囊继续生效。当前锦囊使用者不会被要求无懈自己的收益锦囊，但可以在对方已出无懈后用无懈反制。AI 策略：该用就用，不要为了囤牌而放任敌方收益。判断当前最终状态：如果使用无懈能阻止敌方摸牌、回血、拿牌、拆顺己方、控制己方、造成伤害，就积极使用；如果使用无懈会抵消己方收益或保护敌方收益，通常不要用；如果当前已有一张无懈使己方关键锦囊被抵消，而你再出无懈能让己方锦囊继续生效，应积极反无懈。",
        "lebusishu": "乐不思蜀：置入目标判定区；其判定阶段判定，非红桃则跳过出牌阶段。AI 策略：这是强控制牌，应主动贴给敌方关键输出、主公或最威胁己方阵营的人；不要贴给己方关键角色。",
        "shandian": "闪电：置入自己判定区；判定为黑桃 2-9 时受到 3 点雷电伤害，否则移动给下一名存活角色。AI 策略：高风险高伤害牌，除非需要制造混乱或局势允许，一般低于稳定进攻牌。",
    },
    "equipment": {
        "weapons": "武器进入武器区并替换旧武器，改变攻击范围；诸葛连弩取消杀次数限制，青釭剑无视防具，其余武器在无武将技能版本中主要提供攻击范围。AI 策略：如果当前杀不到关键敌人，优先装备长武器；诸葛连弩配合多张杀很强。",
        "armor": "防具进入防具区并替换旧防具；八卦阵在需要闪时自动判定，红色视为出闪；仁王盾抵消黑色杀；青釭剑无视防具。AI 策略：没有更强进攻动作时应装备防具保命。",
        "horses": "+1 马增加别人到自己的距离，-1 马减少自己到别人的距离。AI 策略：-1 马帮助进攻，+1 马帮助保命；反贼靠近主公时优先 -1 马。",
    },
    "targeting_policy": {
        "zhu": "主公：优先生存。根据行为猜忠臣、反贼、内奸：攻击主公、拆顺主公、无懈主公收益、救反贼的人更像反贼；救主公、无懈伤害主公的锦囊、攻击反贼的人更像忠臣；长期两边削弱、保守自保、避免明显站队的人可能是内奸。攻击疑似反贼，保护疑似忠臣，警惕内奸坐收残局。",
        "zhong": "忠臣：保护主公是最高优先级。不要主动伤害主公，不要使用会伤害主公的群体牌；优先攻击反贼或伤害过主公的人。根据日志找反贼：谁持续压主公、帮压主公的人、无懈主公收益，谁更像反贼。忠臣可以牺牲部分个人收益换主公安全。",
        "fan": "反贼：击败主公是最高优先级。能攻击公开主公时优先主公；不能攻击主公时攻击忠臣或保护主公的人，避免攻击疑似反贼同伴。根据日志找队友：攻击主公、拆顺主公、无懈主公收益、救反贼的人更像反贼同伴；救主公、无懈反贼进攻、攻击反贼的人更像忠臣。没有主公目标时优先打疑似忠臣，不要误杀疑似反贼同伴。",
        "nei": "内奸：优先生存并平衡局势。推断谁是忠臣和反贼，避免过早让任何一方赢；主公太弱时暂缓杀主公或救主公维持局势，反贼太强时打反贼，主忠太强时削弱忠臣或主公资源。残局目标是只剩自己并杀死主公。",
    },
    "role_inference": {
        "evidence_for_rebel": [
            "主动对主公使用杀、决斗、乐不思蜀、过河拆桥、顺手牵羊、借刀杀人。",
            "无懈主公的无中生有、桃园结义回血、五谷丰登拿牌或关键防御收益。",
            "在主公濒死时不救，或救攻击主公的人。",
            "群攻牌明显更伤主公阵营仍然使用。",
        ],
        "evidence_for_loyalist": [
            "救主公、给主公用桃、无懈伤害或控制主公的锦囊。",
            "主动攻击、拆顺、乐不思蜀或决斗疑似反贼。",
            "避免对主公造成伤害，并保护主公装备和手牌。",
        ],
        "evidence_for_rebel_teammate": [
            "同样持续压主公，且没有攻击反贼倾向。",
            "在反贼濒死时出桃救援，或无懈主公阵营对反贼的关键控制。",
            "优先拆顺主公或疑似忠臣，而不是拆顺攻击主公的人。",
        ],
        "evidence_for_spy": [
            "长期不明确站队，只攻击低血或强势一方。",
            "既不稳定保护主公，也不持续压主公，而是让双方消耗。",
            "残局前优先自保、拿装备、保留关键牌，同时削弱领先阵营。",
        ],
        "how_to_use": "把这些证据转化为目标优先级。不要因为身份 unknown 就随机打人；选择最像敌人的目标，尽量避开最像队友的人。如果只有疑似队友目标和结束阶段，通常结束；如果有疑似敌方目标，就积极出牌。",
    },
    "card_choice_policy": {
        "general": "同类多个合法动作时，比较 target_player_name、card_id、selected_area、selected_card_name、距离和当前事件。目标选择比是否出牌同样重要。",
        "damage_targets": "杀、决斗、借刀、南蛮、万箭优先打敌方核心、低体力敌人、手牌少且可能无法响应的人、已经暴露敌意的人。避免打队友，尤其避免忠臣打主公、反贼打疑似反贼同伴。",
        "control_targets": "乐不思蜀优先贴给下回合威胁大、手牌多、有武器、能打己方核心的敌人；不要贴给需要行动救队友的己方角色。",
        "resource_targets": "拆顺优先处理敌方关键公开牌：武器让敌人能打核心、防具阻挡己方攻击、+1马让己方打不到、-1马让敌方能打到己方核心。若公开牌价值不高，敌方手牌少时随机手牌更可能命中关键牌。",
        "equipment_choice": "能立即扩大攻击范围、让杀打到关键目标、解除杀次数限制或提高生存的装备应积极装。已有更好装备时不要为了换装损失关键装备，除非新装备带来即时收益。",
        "wugu_choice": "五谷选牌不是固定优先级。先问：我快死了吗？需要桃/闪/防具；我能马上压敌方核心吗？需要杀/决斗/拆顺/乐/武器；敌方关键锦囊多吗？需要无懈；距离不够吗？需要武器/-1马；需要守住核心队友吗？需要桃/无懈/防具。",
        "discard_choice": "弃牌时保留能影响胜负的牌：低血保留桃、闪、防具；准备进攻保留杀、决斗、拆顺、武器；有敌方强锦囊威胁时保留无懈。弃掉当前难以使用或收益最低的牌。",
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
                "judgment_area": [card.model_dump() for card in target.judgment_area],
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
            "hand": [card.model_dump() for card in player.hand],
        },
        "public_players": public_players,
        "phase": state.phase,
        "pending_response": state.pending_response.model_dump() if state.pending_response else None,
        "recent_events": state.recent_events[-16:],
        "distances": distances,
        "legal_actions": [action.model_dump(exclude_none=True) for action in legal_actions],
        "card_labels": CARD_LABELS,
        "card_rules": CARD_RULES,
        "objective_hint": objective_hint(player.role),
        "role_policy": role_policy(player.role),
        "aggressive_strategy": [
            "总目标是让自己的阵营赢，不是保存手牌。每回合都要寻找能推进胜利的动作。",
            "不要保守。出牌阶段只在没有进攻、控制、补牌、装备、保命收益时才选择 end_phase。",
            "先根据 recent_events 推断每个 unknown 更像反贼、忠臣、内奸还是队友；推断结果会影响目标优先级。",
            "激进不等于乱打。积极进攻敌方和疑似敌方，同时尽量避免伤害推断出的队友或关键盟友。",
            "有合法杀且目标不违反身份禁忌时，优先出杀；反贼能杀主公时必须优先主公，主忠能杀反贼时必须积极杀反贼。",
            "没有杀但有决斗、过河拆桥、顺手牵羊、借刀杀人、乐不思蜀等能压制敌人的动作时，优先选择对阵营胜利收益最大的目标。",
            "同一类动作有多个目标时，不要随机选；选择最像敌方、收益最高、误伤最小的 action_id。",
            "选择五谷丰登公共牌、拆顺区域牌、弃牌组合时，必须比较具体牌的短期收益和阵营收益，而不是机械选择第一项。",
            "有装备且当前没有更高收益攻击动作时，主动装备以扩大后续攻击能力或提高生存能力。",
            "有无懈可击响应机会时，不要默认不出；如果当前锦囊让敌人获得牌、回血、偷牌、控制己方关键角色或伤害己方关键角色，应主动无懈。",
            "濒死、低体力或关键响应时优先保命；但满血或局势允许时不要因为未知身份而空过，不要把 end_phase 当作默认动作。",
        ],
        "decision_guidance": [
            "公开主公是确定信息；unknown 身份不能当作已知身份，只能结合 recent_events 推理。",
            "决策顺序：1) 推断身份倾向；2) 判断当前阶段是否是响应/出牌/弃牌/五谷选择；3) 给每个 legal_action 评估阵营收益；4) 选择收益最高且不违反身份目标的 action_id。",
            "身份推断要看行为而不是座次：攻击谁、救谁、无懈谁的收益、拆顺谁、群攻是否伤到主公、濒死时是否救援，都是证据。",
            "反贼要主动寻找忠臣和反贼同伴：保护主公的人优先打，压主公的人更可能是队友；没有主公目标时优先打疑似忠臣，不要打疑似反贼同伴。",
            "主公要主动区分忠臣、反贼、内奸：保护主公的人更像忠臣，持续压主公的人更像反贼，摇摆削弱强势方的人可能是内奸。",
            "忠臣要把主公安危放在个人收益前；内奸要避免任一阵营过早获胜，残局再追求单独胜利。",
            "所有出牌、响应、弃牌、装备和锦囊目标必须严格来自 legal_actions；不要尝试选择未列出的牌或目标。",
            "legal_actions 中的 card_id/card_name/card_suit/card_rank 指向具体牌；同名牌必须按 action_id 选择，不要假设后端会随机替你挑。",
            "拆顺动作中的 selected_area/selected_card_id 表示目标区域：hand 是随机手牌，equipment/judgment 是公开具体牌。",
            "五谷丰登响应时只能从 wugu_choose 动作里选择公共牌池中的具体 card_id。",
            "五谷丰登选牌时，按当前角色需要选最有用的牌：低血保命选桃/闪/防具；能进攻选杀/决斗/拆顺/乐/武器；需要反制锦囊选无懈；距离不够选武器或-1马。",
            "过河拆桥和顺手牵羊选择区域时，优先处理会改变局势的公开牌；如果公开牌价值不高，再考虑敌方随机手牌。",
            "如果 legal_actions 中存在符合身份目标且不违反 forbidden 的杀，优先出杀；不要在能合理出杀时直接结束阶段。",
            "使用杀、决斗、南蛮入侵、万箭齐发等会造成伤害的动作前，先判断每个目标是否符合你的身份目标。",
            "如果多个攻击目标都合理，优先攻击当前体力更低、对己方目标威胁更高的玩家。",
            "使用桃和无懈可击时按阵营收益判断：该救队友就救，该阻止敌方收益就阻止，该反无懈保护己方关键锦囊就反无懈。",
            "不要因为看不到身份就机械结束阶段；有合理攻击目标时应积极行动。",
        ],
    }
