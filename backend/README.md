# 后端说明

后端使用 FastAPI + Pydantic，实现 v0.1 简化身份局的规则引擎、状态脱敏、AI 决策调用和内存存储。

## 启动

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

## API

- `GET /health`：健康检查。
- `POST /api/games`：创建游戏。
- `GET /api/games/{game_id}`：获取脱敏状态。
- `GET /api/games/{game_id}/legal-actions`：获取当前人类可执行动作。
- `POST /api/games/{game_id}/actions`：提交人类动作。
- `POST /api/games/{game_id}/step-ai`：调试用，推进 AI 一步。

## 测试

```bash
cd backend
pytest
```

## 重要约束

- 后端是唯一裁判。
- 前端和 AI 都只能提交 `action_id`。
- 状态接口不返回 AI `api_key`。
- 状态接口不返回其他玩家手牌。
- 正常创建游戏不传 seed，身份和牌堆都会随机化。

