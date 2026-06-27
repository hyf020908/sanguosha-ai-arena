# 前端说明

前端使用 React + Vite + TypeScript。界面包含新建游戏、玩家状态、手牌、合法动作、事件日志和胜负结果。

## 启动

```bash
cd web
npm install
npm run dev
```

默认后端地址是 `http://localhost:8000`。可以通过环境变量修改：

```bash
VITE_API_BASE_URL=http://localhost:8000 npm run dev
```

## 前端职责

- 展示后端返回的脱敏状态。
- 展示后端返回的合法动作。
- 点击动作时提交 `action_id`。
- 显示 API 错误。

前端不判断动作是否合法，也不推演规则。

