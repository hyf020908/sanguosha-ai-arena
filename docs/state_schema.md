# 状态协议

本文档描述后端返回给前端和 AI 使用的核心状态字段。状态采用字段化结构，规则合法性由后端计算为 `legal_actions`。

## GameState 字段

- `game_id`：游戏 ID。
- `players`：玩家列表。
- `ai_timeout_seconds`：AI 请求超时秒数，默认 30，合法范围 10 到 120。
- `deck_count`：牌堆剩余数量。
- `discard_count`：弃牌堆数量。
- `current_player_index`：当前回合玩家在 `players` 中的索引。
- `phase`：当前阶段，可能是 `judge`、`draw`、`play`、`discard`、`response`、`game_over`。
- `pending_response`：待响应状态，没有待响应时为 `null`。
- `round`：轮数。
- `recent_events`：最近事件，最多保留 30 条。
- `winner`：胜利方，可能是 `zhu`、`fan` 或 `null`。
- `distances`：公开距离矩阵，包含来源、目标、距离、来源攻击范围、目标是否在攻击范围内。
- `legal_actions`：当前人类玩家可执行动作；如果不是人类操作时机，返回空数组。

后端内部还保存完整 `deck` 和 `discard_pile`，但不会把牌堆内容返回给前端。

## Player 字段

- `id`：玩家 ID。
- `name`：玩家名称。
- `is_human`：是否为人类玩家。
- `role`：身份。对不可见身份返回 `unknown`。
- `role_public`：身份是否公开。
- `hp`：当前体力。
- `max_hp`：体力上限。
- `alive`：是否存活。
- `hand`：手牌。只有人类自己的手牌会返回，其他玩家返回空数组。
- `hand_count`：手牌数量。
- `used_sha_this_turn`：本出牌阶段是否已经使用过杀。
- `equipment`：公开装备区，包含 `weapon`、`armor`、`attack_horse`、`defense_horse`。
- `judgment_area`：公开判定区，包含乐不思蜀、闪电等延时锦囊。

后端内部玩家可能包含 `ai_config`，但不会返回给前端。

## Card 字段

- `id`：唯一牌 ID。
- `name`：牌名。v0.2 包含基础牌、锦囊牌、延时锦囊、武器、防具、坐骑。
- `suit`：花色，参与八卦阵、闪电、乐不思蜀、仁王盾等规则。
- `rank`：点数，参与闪电等规则。

## Action 字段

- `action_id`：动作 ID。前端和 AI 必须提交这个字段。
- `type`：动作类型，例如 `play_card`、`equip_card`、`respond_shan`、`respond_sha`、`wuxie`、`discard_cards`。
- `card_id`：相关牌 ID，可为空。
- `card_name`：相关牌名，可为空。
- `target_player_id`：目标玩家 ID，可为空。
- `secondary_target_player_id`：借刀杀人等动作的第二目标，可为空。
- `target_card_ids`：弃牌等动作涉及的多张牌 ID，可为空。
- `target_card_names`：按牌名分组的弃牌动作，可为空。
- `label`：前端显示文本。

后端会校验 `action_id` 是否存在于当前 `legal_actions`，不存在则拒绝执行。

## PendingResponse 字段

- `type`：响应类型，可能是 `respond_shan`、`respond_sha`、`dying_tao`、`discard`、`wuxie`。
- `player_id`：需要响应的玩家 ID。
- `source_player_id`：来源玩家 ID，可为空。
- `origin_player_id`：原始出牌玩家 ID，可为空。
- `target_player_id`：当前效果目标玩家 ID，可为空。
- `secondary_target_player_id`：第二目标玩家 ID，可为空。
- `card_id`：相关牌 ID，可为空。
- `card_name`：相关牌名，可为空。
- `effect_type`：当前结算效果类型，可为空。
- `target_player_ids`：多目标效果的目标列表，可为空。
- `remaining_player_ids`：多目标效果剩余目标列表，可为空。
- `queue_player_ids`：求桃、无懈可击等响应队列，可为空。
- `responded_player_ids`：已响应过的玩家列表，可为空。
- `required_count`：需要弃置的数量，可为空。

## DistanceInfo 字段

- `source_player_id`：距离来源玩家 ID。
- `target_player_id`：距离目标玩家 ID。
- `distance`：来源到目标的当前距离，已计算坐骑修正。
- `attack_range`：来源当前攻击范围，已计算武器。
- `in_attack_range`：目标是否处于来源攻击范围内。

## 人类可见字段

人类玩家可见：

- 自己的身份和手牌。
- 公开的主公身份。
- 所有玩家的名称、体力、存活状态、手牌数量、装备区、判定区。
- 所有存活玩家之间的距离和攻击范围命中关系。
- 当前阶段、当前玩家、最近事件、胜负结果。
- 当前人类可执行的合法动作。

## 不返回给前端的字段

- 其他玩家的具体手牌。
- AI 的 `api_key`。
- AI 的完整配置。
- 牌堆和弃牌堆的具体牌列表。
- 非人类操作窗口中的合法动作。

## 为什么使用 legal_actions

AI 和前端都不自行推演规则。后端根据当前阶段、手牌、装备、判定区、距离、响应链和濒死状态生成 `legal_actions`。人类或 AI 只能提交其中一个 `action_id`，后端执行前会再次校验。
