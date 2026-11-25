# 成员 3 前端交互 · 交接文档

> 项目：个人记账与消费分析 AI 助手（2026 GDUF 人工智能工作室二轮考核 · 方向一 · 选题 A）
> 交接人：成员 3（前端交互）｜接收方：成员 1 / 成员 2 / 成员 4，以及后续接手前端的人
> 契约依据：[`docs/api-contract.md`](./api-contract.md)（字段有变化先改契约，再改前端 `src/types/contract.ts`）

---

## 1. 交接摘要

成员 3 负责的「React 聊天界面、确认卡片、账单列表与 ECharts 统计图」已全部交付，工程位于
[`frontend/`](../frontend/README.md)，可直接 `npm run dev` 联调，也可 `npm run build` 后由 FastAPI 托管。

| 项目 | 状态 |
| --- | --- |
| 前端工程（Vite + React 18 + TS + Tailwind 3 + ECharts 5 + axios） | ✅ 已交付 |
| 对话页：发消息、确认卡片（可编辑）、批量确认、新会话、会话持久化 | ✅ 已交付 |
| 账单页：筛选、编辑（PATCH 变动字段）、删除（二次确认）、移动端布局 | ✅ 已交付 |
| 统计页：类别占比环形图、日/月趋势柱状图、排行榜、时间维度切换 | ✅ 已交付 |
| 预算页：按月查询、进度与 `normal/warning/exceeded` 配色、设置/覆盖预算 | ✅ 已交付 |
| 错误处理：`{code,message,trace_id}` 统一映射、重试、断网提示 | ✅ 已交付 |
| 小票上传（`/api/ocr/upload`） | ⚠️ 前端已写适配 + 降级，**接口未提供，未真实联调**（成员 4） |
| 前端自动化测试（单测 / e2e） | ❌ 未做，仅手工 + headless Chrome 冒烟（见 6 节） |

**本机验收证据**：后端 8010（离线规则模式）+ 构建产物静态托管 8091，Chrome headless 跑通
「发消息 → 生成卡片 → 确认入账（created=1）→ 账单编辑/删除 → 统计切类别/日/月 → 预算设置 → 390px 移动视口」，
`document.scrollWidth` 无横向溢出，页面无 console 报错。TypeScript 与 `vite build` 均通过。

---

## 2. 交付物与阅读顺序

新接手前端的人按这个顺序读，20 分钟能定位一切：

1. `frontend/README.md` —— 启动、目录、页面与接口对照、自测清单、常见问题
2. `src/types/contract.ts` —— 契约的 TypeScript 镜像，**所有字段含义以这里为准**
3. `src/api/client.ts` —— axios 实例、`ApiError`、错误码与兜底文案
4. `src/pages/ChatPage.tsx` —— 最核心的交互（消息、卡片状态机、确认回传）
5. `src/components/ConfirmCard.tsx` —— 卡片可编辑字段与回传结构
6. `src/pages/{Transactions,Stats,Budgets}Page.tsx` —— 三个数据页，模式一致
7. `src/App.tsx`、`src/components/AppShell.tsx` —— 路由与外壳

关键约定（改动前务必知道）：

- 路由是 **hash 模式**（`#/chat`…），为了交给 FastAPI `StaticFiles` 托管时不需要 history fallback。
- 写操作永远先出卡片，`pending_actions` **原样保存**；确认时只改 `draft` 的可编辑字段。
- `session_id` 存 `localStorage['gduf.session_id']`；「新会话」先 `DELETE /api/chat/session/{id}` 再本地清空。
- 金额/日期格式集中在 `src/lib/format.ts`（业务时区 Asia/Shanghai），不要在组件里手写格式化。

---

## 3. 给成员 1（Agent 核心 + 接口）的交接

前端完全按现有契约实现，**没有要求后端新增或修改任何字段**。需要你配合两件事：

### 3.1 托管前端构建产物（部署链路必需）

`docs/tech-stack.md` 约定 `dist` 由 FastAPI 托管。当前 `main.py` 还没有这一段，建议加在所有路由注册之后：

```python
from pathlib import Path
from fastapi.staticfiles import StaticFiles

dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if dist.exists():  # 前端未构建时不影响后端启动
    app.mount("/", StaticFiles(directory=dist, html=True), name="frontend")
```

注意顺序在 `include_router` 之后，否则 `/api/*` 会被静态目录抢先匹配。哈希路由不需要额外 rewrite。

### 3.2 README 与状态同步

我已把根 README 中「前端未开始」的相关表述、技术栈行、目录树、启动说明更新为已交付，
并把前端交接文档加入文档索引。如果成员 1 对 README 有最终排版权，请复核这几处 diff，
以及 `已知问题与未完成部分` 里是否还要补 Docker 相关条目。

### 3.3 契约相关的两个确认点

- 前端把「上传接口不存在」归类为自造错误码 `OCR_UNAVAILABLE`（**仅前端展示用，不进入后端错误表**），
  契约表里的后端错误码未改动。
- 前端对 `intent` 只做展示映射（记账/查账/预算/待确认/闲聊/已拒绝），不做任何业务分支，
  因此后端新增 intent 时前端不会崩，只会显示原值——如需固定展示，请先在契约里加枚举。

---

## 4. 给成员 2（业务与数据）的交接

四个数据接口已全部对接，前端按以下语义使用，请保持这些行为不变：

| 接口 | 前端依赖的行为 |
| --- | --- |
| `GET /api/transactions` | `items` 按日期+ID 倒序；`limit` 1~200；`keyword` 匹配商户或备注；空 `items` 显示空状态 |
| `PATCH /api/transactions/{id}` | **只提交改动字段**（前端做 diff），后端「至少一个字段」校验因此不会误触发；`404 TRANSACTION_NOT_FOUND` 会提示账单已不存在 |
| `DELETE /api/transactions/{id}` | 返回 `{"deleted": true}`；前端删除后不重排列表，仅本地移除 |
| `GET /api/stats` | `items` 已按金额倒序（前端直接用第一条当「最大分类」）；`group_by=day` 的 `key` 是 `YYYY-MM-DD`、`month` 是 `YYYY-MM`；`total` 与 `items` 金额之和一致 |
| `GET /api/budgets` | `usage` 视为**比例**（`spent/budget`，可 >1），前端用 `min(100%, usage*100%)` 画条；`total_budget` 为 `null` 时显示「未设置」；没有 `total` 项时总预算卡片仍可设置 |
| `PUT /api/budgets` | `month + scope` 覆盖语义与前端按钮文案一致（「保存/覆盖」），返回体不参与渲染 |

需要新增字段时：先改 `docs/api-contract.md` → 再改 `frontend/src/types/contract.ts` → 最后改页面。
只改后端不改前端的字段，前端会静默忽略（TS 类型不会报错，但也不会展示），联调时容易漏。

---

## 5. 给成员 4（OCR 与工程）的交接

### 5.1 前端已按下列规格预留上传接口

- `POST /api/ocr/upload`，`multipart/form-data`，文件字段名 **`file`**
- 成功响应：`{"image_id": "<string>"}`（也兼容 `imageId` 驼峰，但请优先用 `image_id`）
- 失败：返回契约统一错误体 `{code,message,trace_id}`；未实现时返回 404/405/501 也可以，前端会显示
  「图片识别接口尚未接入（成员 4 负责），可以先手动告诉我金额和类别。」并允许手动填写 `image_id`
- 建议限制：`image/*`、单文件 ≤ 5MB，返回 413/422 时前端会把 `message` 直接展示给用户

对接到位后，前端无需改代码即可「点回形针上传 → 自动带入 `image_id` → 发消息走 OCR 草稿链路」。
当前 `src/api/ocr.ts` 的容错分支可以直接删除，只保留正常路径。

### 5.2 Docker 多阶段构建

按 `docs/tech-stack.md` 第 10 节，前端在镜像里用 `node:20-alpine` 构建并把 `frontend/dist` 拷进运行镜像；
运行镜像仍需 `frontend/dist` 存在，否则 3.1 的 `app.mount` 不会生效。建议构建阶段：

```dockerfile
FROM node:20-alpine AS web
WORKDIR /web
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build            # 产物 /web/dist
```

并在最终阶段 `COPY --from=web /web/dist /app/frontend/dist`。注意 `npm ci` 依赖已提交的 `package-lock.json`。

### 5.3 真实 OCR 后需要回归的前端点

- 低置信度（`confidence < 0.8`）或 `needs_review` 非空时，卡片会显示黄色「请核对」提示条
- 缺字段时后端先追问，前端不会出现卡片；补全后才出卡（属预期，不要当 bug）
- `source="ocr"` 时卡片头部标签显示「小票识别」，账单列表来源列显示「小票」

---

## 6. 验收与联调步骤（可直接照做）

```bash
# 1) 后端
cd backend && uvicorn app.main:app --reload --port 8000

# 2) 前端
cd frontend && npm install && npm run dev     # http://localhost:5173

# 3) 打开页面，按顺序操作
#    对话页：午饭 25 元 → 确认入账 → 提示「已入账 1 笔」
#    账单页：本月筛选 → 编辑金额 → 删除一笔（二次确认）
#    统计页：按类别 / 按天 / 按月三种维度，总数与账单页合计一致
#    预算页：设置总预算 2000、餐饮 1500 → 进度条与状态变化
#    对话页：点「新会话」，继续输入「这个月餐饮花了多少」仍可正常查账

# 4) 生产形态
cd frontend && npm run build
#    启动 FastAPI 后访问 http://127.0.0.1:8000/ 应直接打开前端页面
```

联调记录请填 `docs/integration-checklist.md` 第 7 节，前端全流程一行可写：

| 日期 | 链路 | 执行人 | 结果 | 证据 |
| --- | --- | --- | --- | --- |
| 2026-11-22 | 前端全流程 | 成员 3 | 通过（OCR 上传除外） | `created=1`、账单/统计/预算截图、Chrome headless 无 console 错误 |

---

## 7. 已知问题与后续待办（按优先级）

1. **未做前端自动化测试**：目前仅手工 + headless 冒烟。若后续要守住回归，建议
   Vitest + Testing Library 覆盖 `ConfirmCard`（回传结构）、`ChatPage`（卡片状态机），
   Playwright 覆盖「记一笔 → 确认 → 账单可见」。
2. **OCR 上传未真实联调**：接口就绪后按 5.1 回归一次，删掉 `src/api/ocr.ts` 的降级分支。
3. **对话历史不持久**：刷新页面后聊天区清空（`session_id` 会保留，后端记忆仍在）。
   若答辩需要「刷新不丢」，可加 `GET /api/chat/messages`——**必须先加契约**，前端不自行假设。
4. **无鉴权、无多用户**：单机演示定位，`session_id` 可被复用；对外部署前需加登录与数据隔离。
5. **ECharts 分块 505 KB（gzip 170 KB）**：已按 `react` / `charts` / 业务拆包；若需再降，
   把统计页改成 `React.lazy` 懒加载即可，不影响其他页面首屏。
6. **未做真机移动端上传验证**：390px 布局与底部导航已验证，iOS Safari 的文件选择与日期控件建议真机再看一次。
7. **图表无下钻**：点击分类不会跳到该类别账单；有需要再加，注意先与成员 2 确认筛选参数。

---

## 8. 本次改动范围（便于 code review）

| 路径 | 说明 |
| --- | --- |
| `frontend/**`（新增） | 前端工程全部代码、`package-lock.json`、`README.md`、`.env.example` |
| `README.md`（修改） | 技术栈行、目录树、启动说明、已知问题、分工表：标记前端已交付 |
| `docs/handoff-member3.md`（新增） | 本交接文档 |
| `.gitignore`（修改） | 追加 `node_modules/`、`frontend/.env.local`、`.vercel` 等前端产物 |

未改动任何后端代码、测试与契约字段；`frontend/dist` 已被 `.gitignore` 忽略，不进仓库。

---

## 9. 交接确认

| 项目 | 交接人 | 接收人 | 说明 |
| --- | --- | --- | --- |
| 前端工程与页面 | 成员 3 | 成员 1（整体集成） | 已在 README 与本文档说明启动/托管方式 |
| 上传接口规格 | 成员 3 | 成员 4 | 见 5.1，就绪后回归 5.3 |
| 数据字段语义 | 成员 3 | 成员 2 | 见第 4 节 |
| 部署与打包 | 成员 3 | 成员 4 | 见 5.2，镜像内需包含 `frontend/dist` |

有疑问先查 `frontend/README.md` 与 `docs/api-contract.md`；仍不明确时，把页面现象 + 浏览器 Network 里的
`{code, trace_id}` 一起发给对应成员，比对后端日志即可定位。
