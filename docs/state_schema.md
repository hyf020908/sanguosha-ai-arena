# 状态协议

本文档描述后端返回给前端和 AI 使用的核心状态字段。状态采用字段化结构，避免传递大段规则文本，减少 token 消耗。

## GameState 字段

- `game_id`：游戏 ID。
- `players`：玩家列表。
- `ai_timeout_seconds`：AI 请求超时秒数，默认 30，合法范围 10 到 120。
- `deck_count`：牌堆剩余数量。
- `discard_count`：弃牌堆数量。
- `current_player_index`：当前回合玩家在 `players` 中的索引。
- `phase`：当前阶段，可能是 `draw`、`play`、`discard`、`response`、`game_over`。
- `pending_response`：待响应状态，没有待响应时为 `null`。
- `round`：轮数。
- `recent_events`：最近事件，最多保留 20 条。
- `winner`：胜利方，可能是 `zhu`、`fan` 或 `null`。
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

后端内部玩家可能包含 `ai_config`，但不会返回给前端。

## Card 字段

- `id`：唯一牌 ID。
- `name`：牌名，可能是 `sha`、`shan`、`tao`。
- `suit`：花色展示字段。
- `rank`：点数展示字段。

花色和点数在 v0.1 不影响规则。

## Action 字段

- `action_id`：动作 ID。前端和 AI 必须提交这个字段。
- `type`：动作类型。
- `card_id`：相关牌 ID，可为空。
- `card_name`：相关牌名，可为空。
- `target_player_id`：目标玩家 ID，可为空。
- `target_card_ids`：弃牌等动作涉及的多张牌 ID，可为空。
- `label`：前端显示文本。

后端会校验 `action_id` 是否存在于当前 `legal_actions`，不存在则拒绝执行。

## PendingResponse 字段

- `type`：响应类型，可能是 `respond_shan`、`dying_tao`、`discard`。
- `player_id`：需要响应的玩家 ID。
- `source_player_id`：来源玩家 ID，可为空。
- `card_id`：相关牌 ID，可为空。
- `required_count`：需要弃置的数量，可为空。

## 人类可见字段

人类玩家可见：

- 自己的身份和手牌。
- 公开的主公身份。
- 所有玩家的名称、体力、存活状态、手牌数量。
- 当前阶段、当前玩家、最近事件、胜负结果。
- 当前人类可执行的合法动作。

## 不返回给前端的字段

- 其他玩家的具体手牌。
- AI 的 `api_key`。
- AI 的完整配置。
- 牌堆和弃牌堆的具体牌列表。
- AI 操作窗口中的手牌相关合法动作。

## 为什么用字段化状态节省 token

AI 决策不需要完整规则文档。后端会把规则计算成 `legal_actions`，AI 只需要知道局面摘要、自己的手牌、公开玩家信息和可选动作。这样可以减少每次请求的 token，并避免 AI 自行解释规则导致越权动作。
