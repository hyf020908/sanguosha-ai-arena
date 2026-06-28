# 后端说明

后端使用 FastAPI + Pydantic，实现 v0.2 身份局规则引擎、标准牌型结算、状态脱敏、AI 决策调用和内存存储。

## 启动

需要 Python 3.10 或更高版本，推荐 Python 3.11+。如果默认 `python` 版本过低，请用 `python3.11` 创建项目虚拟环境。

```bash
cd backend
../.venv/bin/python -m pip install -r requirements.txt
PYTHONPATH=. ../.venv/bin/uvicorn app.main:app --reload --port 8000
```

## API

- `GET /health`：健康检查。
- `POST /api/games`：创建游戏。
- `GET /api/games/{game_id}`：获取脱敏状态。
- `GET /api/games/{game_id}/legal-actions`：获取当前人类可执行动作。
- `POST /api/games/{game_id}/actions`：提交人类动作。

## 测试

```bash
cd backend
pytest
```

## 重要约束

- 后端是唯一裁判。
- 前端和 AI 都只能提交 `action_id`。
- v0.2 包含基础牌、锦囊牌、延时锦囊、装备牌、距离、响应链、濒死求桃、五谷公共牌池、无懈链、身份胜负和死亡奖惩。
- 所有出牌、响应、弃牌和装备动作都绑定具体 `card_id`，执行前会再次校验当前 `legal_actions`。
- 当前版本不加入武将、英雄技能或官方素材。
- 状态接口不返回 AI `api_key`。
- 状态接口不返回其他玩家手牌。
- 正常创建游戏不传 seed，身份和牌堆都会随机化。
- 创建游戏可配置 AI 请求超时秒数，合法范围为 10 到 120，非法值按 30 处理。
