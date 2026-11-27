# 前端工程（成员 3 交付物）

React + TypeScript + Vite 前端，覆盖**对话记账 / 账单流水 / 消费统计 / 月度预算**四个页面。
所有字段严格按 [`docs/api-contract.md`](../docs/api-contract.md) 绑定，不新增后端未定义的字段。

## 快速开始

```bash
cd frontend
npm install
npm run dev          # http://localhost:5173，/api 自动代理到 http://127.0.0.1:8000
```

后端需先启动（仓库根目录）：

```bash
cd backend
uvicorn app.main:app --reload --port 8000
```

未配置 `LLM_API_KEY` 时后端运行在离线规则模式，左侧状态胶囊会显示「离线规则模式」，前端功能不受影响。

### 构建与部署

```bash
npm run build        # 产物在 frontend/dist
npm run preview      # 本地预览构建产物
npm run typecheck    # 仅类型检查
```

部署形态按 [`docs/tech-stack.md`](../docs/tech-stack.md) 第 6 节：`dist` 由 FastAPI 托管到 `/`，
因此路由使用 **hash 模式**（`#/chat`、`#/transactions`、`#/stats`、`#/budgets`），
不需要服务端做 history fallback。

`backend/app/main.py` 已实现该挂载（目录存在才挂，且放在 `create_app()` 末尾，避免 `/` 抢掉 `/api/*` 路由），
因此 `npm run build` 之后直接起 FastAPI，访问 <http://127.0.0.1:8000/> 就是完整页面；
未构建时后端仍可正常启动，只是 `/` 返回 404。

开发期不走托管：Vite 代理 `/api`，因此前端不需要处理跨域（后端已开 CORS 全放通）。

## 环境变量

| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `VITE_API_BASE` | `/api` | 接口前缀；只在需要直连其他地址时设置（例如 `http://127.0.0.1:8000/api`） |
| `VITE_PROXY_TARGET` | `http://127.0.0.1:8000` | 仅开发服务器使用，代理目标 |

模板见 `frontend/.env.example`，实际使用复制成 `.env.local`（已在 `.gitignore` 中忽略）。

## 目录结构

```text
frontend/
├── index.html
├── package.json / package-lock.json    # 锁文件需提交
├── vite.config.ts                      # 端口 5173 + /api 代理 + 手动分包
├── tailwind.config.js / postcss.config.js
├── .env.example
└── src/
    ├── main.tsx / App.tsx              # 入口与 hash 路由、健康检查轮询
    ├── index.css                       # Tailwind 层与设计令牌
    ├── api/                            # axios 封装，按后端模块拆分
    │   ├── client.ts                   # baseURL、拦截器、ApiError、请求助手
    │   ├── chat.ts                     # /api/chat、/confirm、/session、/health
    │   ├── transactions.ts             # /api/transactions
    │   ├── stats.ts                    # /api/stats
    │   ├── budgets.ts                  # /api/budgets
    │   └── ocr.ts                      # /api/ocr/upload（成员 4 未就绪时降级）
    ├── types/contract.ts               # 与 api-contract.md 一一对应的类型
    ├── lib/{format,categories}.ts      # 金额/日期格式化、类别体系与配色
    ├── hooks/{useSession,useChart}.ts  # 会话持久化、ECharts 实例管理
    ├── components/                     # AppShell、确认卡片、模态框、错误条、图表
    └── pages/                          # ChatPage、TransactionsPage、StatsPage、BudgetsPage
```

## 页面与接口对应

| 页面 | 交互 | 使用接口 |
| --- | --- | --- |
| 对话记账 | 发消息、上传小票、确认卡片编辑与批量确认、清空会话 | `POST /api/chat`、`POST /api/chat/confirm`、`DELETE /api/chat/session/{id}`、`GET /api/health` |
| 账单流水 | 日期/类别/关键词/条数筛选，编辑（只提交改动字段）、删除 | `GET /api/transactions`、`PATCH /api/transactions/{id}`、`DELETE /api/transactions/{id}` |
| 消费统计 | 时间范围与快速区间、类别/日/月维度、占比环形图与趋势柱状图、排行榜 | `GET /api/stats` |
| 月度预算 | 按月查询总预算与分类预算进度、设置/覆盖预算 | `GET /api/budgets`、`PUT /api/budgets` |

### 关键契约行为（已实现）

1. `session_id`：首次响应返回后写入 `localStorage`（键 `gduf.session_id`），后续请求一直回传；
   「新会话」先调 `DELETE /api/chat/session/{id}`，再本地清空并清除存储。
2. `pending_actions`：**原样保存**在消息里；确认时只在卡片内改写 `draft` 的可编辑字段
   （`amount` / `category` / `merchant` / `occurred_at` / `note`），`source`、`confidence`、
   `needs_review`、`action`、`transaction_id`、`patch` 保持后端返回值。
3. `confirm_required`：为 `true` 时一定渲染确认卡片；`false` 时不渲染任何写入按钮。
4. 卡片缺字段（金额/类别/日期）时禁用「确认入账」并提示，避免产生必然失败的确认请求。
5. `needs_review` 或 `confidence < 0.8` 时展示核对提示条（小票识别场景）。
6. 修改账单只提交与服务端不一致的字段，满足 PATCH「至少一个字段」的校验。

## 错误处理

- axios 拦截器把 `{code,message,trace_id}` 与网络异常统一成 `ApiError`（`src/api/client.ts`），
  页面只处理一种错误形状，错误条同时展示 `code` 与 `trace_id` 便于按契约排查。
- `5xx` / 网络错误显示「重试」按钮（对话页会重发上一条消息，列表页重新拉取）。
- `503 LLM_UNAVAILABLE`：提示先手动记账；`422`：提示检查参数；`404 TRANSACTION_NOT_FOUND`：提示账单已不存在。
- 小票上传对接 `POST /api/ocr/upload`（multipart 字段 `file`）：前端先校验 JPG/PNG/WEBP 与 10MB 上限，
  服务端的 `INVALID_FILE_TYPE`(415) / `FILE_TOO_LARGE`(413) / `EMPTY_FILE`(422) 文案直接透传；
  接口不可用或网络异常时才提示手动填写 `image_id` 兜底。

## 自测清单（对照 docs/integration-checklist.md）

- [x] 说话生成确认卡片 → 确认 → 账单页出现该笔（`created=1`）
- [x] 卡片内改金额/类别/日期后确认，入账值以修改后为准
- [x] 多笔消息出现多张卡片，支持「全部确认」
- [x] 账单页按本月/上月/近 30 天/全部筛选，关键词与类别过滤生效
- [x] 账单页编辑只提交变动字段；删除有二次确认
- [x] 统计页类别占比、按天/按月趋势、排行榜与总数一致
- [x] 预算页按月查询、设置后即时刷新，`normal/warning/exceeded` 三色与进度条对应
- [x] 断开后端时聊天与列表均显示网络错误条，恢复后可重试
- [x] 1280px 与 390px 视口无横向滚动，移动端使用底部标签导航
- [x] `npm run build` 通过（tsc + vite），产物由 FastAPI 静态托管可直接打开

> 验证方式：本机用 Windows Python 起后端 8010 + 构建产物静态托管 8091，Chrome headless 走完
> 「发消息 → 确认入账 → 账单编辑/删除 → 统计切换维度 → 预算设置 → 移动视口」全流程，
> 页面无 console 错误。前端尚未引入自动化测试（见交接文档待办）。

## 常见问题

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| 页面显示「后端未连接」 | uvicorn 未启动或端口不是 8000 | 起后端，或用 `VITE_PROXY_TARGET` 指向实际端口 |
| 接口 404 | `VITE_API_BASE` 被设成带 `/api/api` | 保持默认 `/api` |
| 图表空白 | 该范围无数据，或切到了日/月维度 | 换范围；日/月维度看右侧趋势图 |
| 刷新后对话消失 | 对话内容只存在前端内存，后端仅存消息记忆 | 属预期；账单/统计/预算来自数据库不受影响 |
| 上传小票返回 415/413 | 格式不是 JPG/PNG/WEBP，或超过 10MB | 换图或压缩后重试（前端已做同样的预校验） |
| 识别结果总是「沙县小吃 25 元」 | 未配置 `VISION_API_KEY`，OCR 退回桩实现 | 配 `.env` 的视觉模型信息，或按桩数据演示 |
