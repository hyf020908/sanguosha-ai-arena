# AI 决策协议

AI 玩家通过 OpenAI-compatible Chat Completions API 决策。AI 不判断动作是否合法，只能从后端生成的 `legal_actions` 中选择一个 `action_id`。

## Prompt 结构

system prompt 会要求模型：

- 这是 v0.2 无武将、无英雄技能的三国杀身份局。
- 只能选择 `legal_actions` 中已有的 `action_id`。
- 不能发明手牌、目标、技能、额外响应或未列出的动作。
- 必须遵守身份目标和 `role_policy.forbidden`。
- 如果存在符合身份目标且不违反禁止策略的 `杀`，强烈倾向于选择 `杀`，不要直接结束阶段。
- 后端只生成规则合法动作，并可按公开信息做轻量排序；具体策略选择由 LLM 完成，后端不使用隐藏身份替 AI 删除救援、无懈、攻击或控制动作。
- Prompt 会额外提供 `aggressive_strategy`，明确要求 AI 不要保守，能推进身份目标时主动行动。
- 遇到 `respond_shan`、`respond_sha`、`dying_tao`、`wuxie` 等响应时，只能在后端列出的响应动作中选择。
- 所有使用、响应、装备和弃牌动作都绑定具体 `card_id`；同名牌不能混用，必须选择对应 action_id。
- 无懈可击支持链式反制，五谷丰登使用公共牌池逐人选择；AI 不需要自行结算，只需从当前 `legal_actions` 选择。
- 返回严格 JSON。

user prompt 是紧凑 JSON，包含：

- `you`：当前 AI 的身份、体力和手牌摘要，包含自己手牌的 `id`、`name`、`suit`、`rank`。
- `public_players`：公开玩家信息、体力、手牌数、装备区、判定区。
- `phase`：当前阶段。
- `pending_response`：当前响应上下文。
- `recent_events`：最近事件。
- `distances`：全员公开距离、攻击范围和是否可攻击。
- `legal_actions`：后端生成的合法动作列表，包含 `card_id`、`card_name`、`card_suit`、`card_rank`、目标名称、拆顺选择区域、公开选择牌等结构化信息。
- `valid_action_ids`：最终可选动作集合。模型最终返回值必须逐字来自这里。
- `card_labels`：牌名映射。
- `card_rules`：v0.2 已实现牌型规则摘要。
- `objective_hint`：身份目标提示。
- `role_policy`：身份策略和禁止行为。
- `decision_guidance`：决策约束和目标选择建议。

## AI 只能选择 legal_actions

AI 返回的 `action_id` 必须存在于 `legal_actions` 和 `valid_action_ids`。后端执行动作前会再次校验。如果 AI 输出了不存在的动作，后端会重试一次；仍然失败则执行默认动作。AI 不能只说“出杀”或“使用桃”，必须返回某个包含具体牌 ID 的合法动作，例如 `respond_sha:c33` 或 `dying_tao:c71`。

后端不会把其他隐藏身份直接暴露给 LLM。`public_players` 中除当前 AI 自己和公开主公外，身份均为 `unknown`；`legal_actions` 中的目标身份如果是 `unknown`，模型只能根据 `recent_events` 推断，不能当作已知身份。

濒死求桃时，如果同时存在 `dying_tao:<card_id>` 和 `pass_response`，模型必须根据公开信息和 `recent_events` 推理是否救人。无懈响应时，如果同时存在 `wuxie:<card_id>` 和 `pass_response`，模型也必须根据公开信息和 `recent_events` 判断是否无懈。

前端也只展示后端返回给人类玩家的 `legal_actions`，因此“不允许出的牌”不会出现在按钮区。

## AI 返回 JSON 格式

AI 必须返回严格 JSON：

```json
{
  "action_id": "end_phase",
  "reason": "当前没有更好的出牌"
}
```

`reason` 只用于调试和解释，后端不会根据理由执行任何规则。

## 错误处理和 fallback

以下情况会触发 fallback：

- 请求 AI 服务失败。
- AI 返回不是合法 JSON。
- JSON 中没有 `action_id`。
- `action_id` 不在当前 `legal_actions` 中。

后端最多重试 1 次。仍失败时，后端会优先选择安全动作，例如保命响应、结束阶段、不响应锦囊，或弃牌阶段的一个合法弃牌组合。濒死求桃时，AI 自己濒死会默认自救；别人濒死则默认不救，除非 LLM 成功选择 `dying_tao:<card_id>`。无懈响应默认不使用无懈，除非是明确作用于自己的公开自保场景。

后端不会在日志中打印完整 `api_key`，状态接口也不会回显 `api_key`。

## 示例 prompt

```json
{
  "you": {
    "id": "p2",
    "role": "fan",
    "hp": 3,
    "max_hp": 4,
    "hand": [
      { "id": "c12", "name": "sha", "suit": "spade", "rank": "7" },
      { "id": "c18", "name": "wuxiekeji", "suit": "club", "rank": "Q" }
    ]
  },
  "public_players": [
    {
      "id": "p0",
      "name": "Human",
      "hp": 5,
      "max_hp": 5,
      "role": "zhu",
      "hand_count": 4,
      "equipment": { "weapon": null, "armor": null, "attack_horse": null, "defense_horse": null },
      "judgment_area": [],
      "alive": true
    }
  ],
  "phase": "play",
  "pending_response": null,
  "recent_events": ["Human 结束回合"],
  "legal_actions": [
    {
      "action_id": "play_sha:c12:p0",
      "type": "play_card",
      "card_id": "c12",
      "card_name": "sha",
      "card_suit": "spade",
      "card_rank": "7",
      "target_player_id": "p0",
      "target_player_name": "Human"
    },
    { "action_id": "end_phase", "type": "end_phase" }
  ],
  "card_rules": {
    "basic": {
      "sha": "出牌阶段对攻击范围内一名其他角色使用；通常每阶段限一次，装备诸葛连弩时不限次数。"
    }
  },
  "objective_hint": "你是反贼。优先击败主公。"
}
```

## 示例 response

```json
{
  "action_id": "play_sha:c12:p0",
  "reason": "反贼优先压低主公体力"
}
```

## 多模型配置说明

每个 AI 都有独立配置：

- `base_url`：OpenAI-compatible 服务地址。
- `api_key`：鉴权 token。
- `model`：模型名称。
- `temperature`：温度，默认 `0.2`。

因此同一局中可以让不同 AI 使用不同模型或不同服务提供方。

创建游戏时还有一个整局共享的 AI 请求超时秒数，默认 `30`，合法范围是 `10` 到 `120`。后端会关闭环境代理读取，直接请求配置的中转站或模型服务地址。
