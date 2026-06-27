# sanguosha-ai-arena

`sanguosha-ai-arena` 是一个“人与 AI 玩三国杀”的开源项目。

本项目不使用任何三国杀官方图片、官方卡面或官方素材。前端只使用自制的文字卡牌 UI。

## 当前版本(v0.1)项目特性

- 人类玩家 + 1 到 5 个 AI，合计 2 到 6 人。
- 简化身份局：主公、忠臣、反贼、内奸。
- 仅实现基础牌：杀、闪、桃。
- 每局随机身份、随机洗牌、随机发牌。
- 后端唯一负责规则判断和动作合法性校验。
- 前端只展示状态和提交 `action_id`。
- AI 通过 OpenAI-compatible Chat Completions API 决策。
- 每个 AI 可单独配置 `base_url`、`api_key`、`model`、`temperature`。
- 创建游戏时可配置 AI 请求超时秒数，范围为 10 到 120，默认 30。
- 返回给前端的状态会脱敏：不泄露其他玩家手牌，不回显 AI `api_key`。

## 新增内容
### 2026.06.27
- 优化前端玻璃拟态效果和字体效果
- 优化模型推理逻辑，让模型决策更具多样性

## 快速启动

建议先启动后端，再启动前端。

### 后端启动

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
./.venv/bin/uvicorn app.main:app --reload --port 8000
```

健康检查：

```bash
curl http://localhost:8000/health
```

### 前端启动

```bash
cd web
npm install
npm run dev
```

前端默认连接 `http://localhost:8000`。如需修改后端地址，可设置 `VITE_API_BASE_URL`。

## AI 配置说明

新建游戏时，每个 AI 都可以单独配置：

- `name`：AI 展示名称。
- `base_url`：OpenAI-compatible 服务地址，例如 `http://localhost:8000/v1`。
- `api_key`：鉴权 token，前端提交给后端后不会在状态接口中回显。
- `model`：模型名称，例如 `qwen`。
- `temperature`：温度，默认 `0.2`。

创建游戏页面还提供全局 AI 请求超时秒数，默认 `30`，最小 `10`，最大 `120`。非法输入会按 `30` 处理。

## OpenAI-compatible 接口说明

后端会请求：

```text
POST ${base_url}/chat/completions
Authorization: Bearer ${api_key}
```

请求体使用 Chat Completions 常见结构：`model`、`messages`、`temperature`、`max_tokens`，并要求模型返回 JSON。AI 只能返回：

```json
{
  "action_id": "play_sha:c12:p0",
  "reason": "简短理由"
}
```

后端只执行 `action_id`，不会执行自由文本理由。

## 项目结构

```text
sanguosha-ai-arena/
  backend/   FastAPI 后端、规则引擎、AI 客户端、测试
  web/       React + Vite + TypeScript 前端
  docs/      规则文档、状态协议、AI 协议
```

## 架构说明

本项目采用“后端规则引擎 + AI 合法动作选择”的架构。原因很简单：AI 输出不稳定，前端也不应该成为裁判。所有玩家动作都必须先由后端生成 `legal_actions`，人类或 AI 只能提交其中某个 `action_id`。这样可以保证规则边界清晰，非法动作会被拒绝。

AI Prompt 使用字段化状态而不是完整规则文档。后端只发送当前 AI 需要的信息：自己的手牌、公开玩家信息、最近事件、阶段、合法动作和目标提示。这能减少 token 消耗，也能降低模型误读规则的概率。

## License

MIT License，copyright (c) 2026 hyf020908。

## 后续待实现功能
- 完善所有卡牌类型，而不局限于杀、闪、桃
- 反复迭代优化模型推理效果以及提示词约束、后端约束
- 加入英雄选择的功能，加入技能
