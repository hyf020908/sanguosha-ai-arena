# AI 决策协议

AI 玩家通过 OpenAI-compatible Chat Completions API 决策。AI 不判断规则，只能从后端生成的 `legal_actions` 中选择一个 `action_id`。

## Prompt 结构

system prompt 固定为：

```text
You are an AI player in a simplified Sanguosha game. You must choose exactly one action_id from legal_actions. Return strict JSON only.
```

user prompt 是紧凑 JSON，包含：

- `you`：当前 AI 的身份、体力和手牌摘要。
- `public_players`：公开玩家信息。
- `phase`：当前阶段。
- `recent_events`：最近事件。
- `legal_actions`：后端生成的合法动作列表。
- `objective_hint`：身份目标提示。

## AI 只能选择 legal_actions

AI 返回的 `action_id` 必须存在于 `legal_actions`。后端执行动作前会再次校验。如果 AI 输出了不存在的动作，后端会重试一次；仍然失败则执行默认动作。

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

后端最多重试 1 次。仍失败时，后端会优先选择安全动作，例如结束阶段、不出闪、不使用桃，或弃牌阶段的一个合法弃牌组合。

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
      { "id": "c12", "name": "sha" },
      { "id": "c18", "name": "shan" }
    ]
  },
  "public_players": [
    { "id": "p0", "name": "Human", "hp": 5, "max_hp": 5, "role": "zhu", "hand_count": 4, "alive": true },
    { "id": "p1", "name": "AI-1", "hp": 4, "max_hp": 4, "role": "unknown", "hand_count": 3, "alive": true }
  ],
  "phase": "play",
  "recent_events": ["Human 结束回合"],
  "legal_actions": [
    { "action_id": "play_sha:c12:p0", "type": "play_card", "card_name": "sha", "target_player_id": "p0" },
    { "action_id": "end_phase", "type": "end_phase" }
  ],
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

