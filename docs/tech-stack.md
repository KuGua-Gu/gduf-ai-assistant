# 项目全技术栈（v1.0）

> 适用范围：个人记账与消费分析 AI 助手（2026 GDUF 人工智能工作室二轮考核 · 方向一 · 选题 A）
> 状态：后端 Agent 部分已按本文实现并通过测试；前端、业务 SQLite、OCR、Docker 为组内约定方案，由对应成员按本文落地。
> 维护人：成员 1（Agent 核心），其他成员变更选型时请同步更新本文。

## 1. 定位与设计原则

一句话：把「说一句话 / 拍一张小票」稳定地变成结构化账单，并让查账、统计、预算都建立在真实入库的数据上。

| 原则 | 落地方式 |
| --- | --- |
| 先跑通再优化 | 未配置模型 Key 时降级为离线规则模式，保证任何环境都能演示完整链路 |
| 模型只做理解，不做事实来源 | 查账/统计必须走工具查库，禁止模型凭上下文编数字 |
| 写操作必须可控 | 记账先生成确认卡片，用户确认后才落库 |
| 依赖可替换 | LLM 走 OpenAI 兼容协议；业务层与 OCR 均以 Protocol 注入，可换实现 |
| 可复现 | 固定版本、`.env.example`、单命令启动、预留 Docker 构建（成员 4） |

## 2. 总体架构

```text
┌──────────────────────────── 前端（成员 3） ────────────────────────────┐
│ React + TypeScript + Vite  │ 聊天窗口 │ 确认卡片 │ 账单列表 │ ECharts 统计 │
└───────────────────────────────┬────────────────────────────────────────┘
                                │ HTTP / JSON（docs/api-contract.md）
┌───────────────────────────────▼────────────────────────────────────────┐
│ FastAPI（成员 1）                                                       │
│  /api/chat · /api/chat/confirm · /api/chat/session/{session_id} · /api/health        │
│  ┌──────────────┐   ┌──────────────┐   ┌───────────────────────────┐   │
│  │ Orchestrator │──▶│ ToolRegistry │──▶│ TransactionService（成员2）│   │
│  │ 意图/槽位/循环│   │ 7+1 工具      │   │ SQLite：账单/预算          │   │
│  └──────┬───────┘   └──────┬───────┘   └───────────────────────────┘   │
│         │                  │                                           │
│  ┌──────▼───────┐   ┌──────▼───────┐   ┌───────────────────────────┐   │
│  │ LLMClient    │   │ Safety       │   │ OcrService（成员 4）       │   │
│  │ OpenAI 兼容   │   │ 越界拒绝      │   │ 视觉模型 / PaddleOCR       │   │
│  └──────────────┘   └──────────────┘   └───────────────────────────┘   │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │ MemoryStore：SQLite agent_sessions / agent_messages + 摘要压缩     │  │
│  └──────────────────────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────────────────────┘
```

## 3. 技术域总表

> 说明：本表按「技术域」统计，不按人统计。同一域可能多人协作（如 Pydantic 模型被四人复用），因此不能把行数当工作量；人均技术栈与工作量对照见 3.1。

| 技术域 | 技术 | 版本 | 主责 / 协作 | 选型理由 |
| --- | --- | --- | --- | --- |
| 后端运行时与 Web 框架 | Python + FastAPI + Uvicorn | 3.11 / 0.115.6 / 0.34.0 | 成员 1 | 自带 OpenAPI 文档，Pydantic 校验开箱即用 |
| 契约与配置 | Pydantic + pydantic-settings | 2.10.4 / 2.7.1 | 成员 1 主责，成员 2/3/4 复用模型 | 工具参数、接口契约、环境变量共用一套类型 |
| 模型接入 | openai SDK（OpenAI 兼容） | 1.59.6 | 成员 1 | 一家 SDK 可切 DeepSeek / 智谱 / 通义 |
| Agent 会话记忆 | SQLite + sqlite3（`agent_*` 表） | 3.40+ | 成员 1 | 与业务表解耦，摘要压缩成本低 |
| 业务数据层 | SQLAlchemy + SQLite（WAL） | 2.0.36 | 成员 2 | 2.x 类型化写法，后续可平滑换 Postgres |
| 统计与预算 | SQL 聚合（GROUP BY）+ csv 标准库 | — | 成员 2 | 统计口径落在数据库，避免模型编数字 |
| 前端框架与构建 | React + TypeScript + Vite | 18 / 5 / 6 | 成员 3 | 组件化 + 类型约束，构建产物可由 FastAPI 托管 |
| 可视化与交互 | ECharts + axios + Tailwind | 5 / 1.x / 3 | 成员 3 | 分类占比、月度趋势现成组件 |
| OCR / 视觉 | 视觉大模型 API + Pillow；PaddleOCR 兜底 | 按账号 / 11.x / 2.8+ | 成员 4 | 小票版式杂，视觉模型鲁棒性优于模板 OCR |
| 部署与上传 | Docker + docker-compose；python-multipart | 24+ / v2 / 0.0.20 | 成员 4 主责，成员 1 配合接口 | 一条命令起服务，满足复现要求 |
| 测试与质量 | pytest（mock / live）+ 手动验收清单 | 8.3.4 | 成员 1 主责，全员补用例 | 参数化跑 30 条评测集，fixture 隔离临时库 |

### 3.1 成员技术栈对照

每人 6 项、按「职责深度」而非「库数量」衡量，避免出现某人只挂两个库、某人挂八个库的错觉。

| 成员 | 技术栈（各 6 项） | 核心产出 | 深度 | 主要难点 |
| --- | --- | --- | --- | --- |
| 成员 1 | FastAPI 路由与异常处理、Pydantic 契约建模、OpenAI function calling、超时重试与降级、SQLite 会话与摘要、pytest 双模式 | Agent 编排 + HTTP 接口 + 30 条评测集 | 高 | 模型输出不稳定、工具循环可控、无 Key 时仍可演示 |
| 成员 2 | 表结构与索引设计、SQLAlchemy 2.x、聚合 SQL（类别/日/月）、预算状态判定、CSV 示例数据导入、业务单测 | SQLite 业务层与统计接口 | 高 | 金额精度、时间区间边界、唯一键与幂等 |
| 成员 3 | React 组件化、TypeScript 类型、axios 封装与错误处理、可编辑确认卡片、ECharts 占比/趋势、响应式与构建 | 聊天、账单、统计、预算四类页面 | 高 | 草稿修改回传、加载与错误态、图表联动 |
| 成员 4 | 图片上传与校验、视觉模型 Prompt、PaddleOCR 兜底、字段抽取与置信度、Dockerfile/compose、复现自检 | OCR 服务 + 容器化交付 | 高 | 小票版式差异、外部服务失败、镜像与数据卷 |

> 结论：成员 2 的库最少（2 个），但其数据设计与统计口径是「正确性深水区」；成员 1 的库最多，是因为后端 Web、模型、记忆、测试都落在同一角色上。按交付风险与工作量衡量，四人基本相当，答辩时按此表述即可。

## 4. 后端技术栈（成员 1 已实现）

- 分层：`api/`（HTTP）→ `agent/`（编排、工具、Prompt、记忆）→ `services/`（业务协议与实现）。
- 配置：全部走 `app/config.py` 的 `Settings`，字段与 `.env.example` 一一对应；`.env` 不入库。
- 模型调用：`app/agent/llm_client.py`，原生 function calling 为主，JSON 模式为兜底；超时 30s、指数退避重试 2 次（仅超时/429/5xx）、累计 Token 统计、Key 脱敏日志。
- 运行时降级：`LLM_API_KEY` 未配置时自动使用 `RuleBasedLLM`，`/api/health` 返回 `llm_configured:false`。
- 错误格式：统一 `{"code","message","trace_id"}`，错误码见 `docs/api-contract.md`。
- 编码与规范：UTF-8；模块按功能拆分，单文件不超过约 400 行；关键函数有中文 docstring。

## 5. 大模型与 Prompt 策略

| 项 | 方案 |
| --- | --- |
| 协议 | OpenAI Chat Completions 兼容（`/v1/chat/completions`） |
| 默认供应商 | DeepSeek `deepseek-chat`；可切智谱 `glm-4-flash`、通义 `qwen-plus` |
| 工具调用 | 原生 function calling，单轮最多 4 次工具调用 |
| 意图范围 | `record_expense` / `query_stats` / `manage_budget` / `confirm_action` / `chitchat` / `refuse` |
| 输出约束 | system prompt 注入当前日期、类别体系、工具优先级、禁止编造、回复 ≤120 字 |
| 失败处理 | JSON 修复重试 1 次 → 固定引导话术；工具参数非法 → 错误回填给模型自纠 |
| 不可用兜底 | 503 + 可读话术 + 引导手动记账 |

## 6. 前端技术栈（成员 3 约定方案）

- 工程：Vite + React 18 + TypeScript 5，目录 `frontend/src/{pages,components,api,types}`。
- 页面与组件：聊天窗口、记账确认卡片（可编辑金额/类别/日期/备注）、账单列表、分类占比与月度趋势图、预算设置页。
- 状态与请求：`axios` 实例统一 baseURL `/api`，拦截器读取 `{code,message,trace_id}`；会话 `session_id` 存 `localStorage`。
- 错误提示：网络错误、模型不可用（503）、参数错误（422）三类分别给出文案与重试按钮。
- 部署方式：`npm run build` 产物由 FastAPI `StaticFiles` 托管到 `/`，避免多容器跨域。

## 7. OCR 与视觉（成员 4 约定方案）

- 上传：前端 `POST /api/ocr/upload`（`multipart/form-data`）→ 返回 `image_id`，文件存 `data/uploads/`。
- 识别：实现 `OcrService.recognize(image_id) -> OcrResult{amount, merchant, occurred_at, confidence, raw}`；Agent 通过 `ocr_receipt` 工具或直接注入草稿。
- 主方案：视觉大模型 API（OpenAI 兼容多模态或供应商原生 SDK），Prompt 要求只输出 JSON 字段。
- 兜底：PaddleOCR 文本 + 规则抽取（金额正则、商户首行、日期正则）；置信度低于 0.8 标记 `needs_review`。
- 安全：图片不入 Git；只保留最近 N 天；接口限制大小与 MIME 类型。

## 8. 数据层约定

| 表 | 负责 | 关键字段 |
| --- | --- | --- |
| `transactions` | 成员 2 | id、amount、category、merchant、occurred_at、note、source(text/ocr/manual)、created_at |
| `budgets` | 成员 2 | id、month(YYYY-MM)、scope(total/类别)、amount、created_at，唯一键 (month, scope) |
| `agent_sessions` | 成员 1 | id、summary、state_json、created_at、updated_at |
| `agent_messages` | 成员 1 | id、session_id、role、content、created_at |

- 索引：`transactions(occurred_at)`、`transactions(category)`、`agent_messages(session_id)`。
- 连接：SQLite 开启 `journal_mode=WAL`、`busy_timeout=5000`、`foreign_keys=ON`。
- 初始化：`backend/app/db/init_db.py`（成员 2）建表 + 导入示例账单 CSV；不引入 Alembic，避免小项目过度设计。
- 时间：一律存 ISO-8601 字符串或 DATE，业务时区固定 `Asia/Shanghai`。

## 9. 接口契约

以 [docs/api-contract.md](api-contract.md) 为准，核心端点：

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| POST | `/api/chat` | 文本/图片对话，返回意图、回复、确认卡片 |
| POST | `/api/chat/confirm` | 确认入账 / 修改 / 删除 |
| DELETE | `/api/chat/session/{id}` | 新会话 |
| GET | `/api/health` | 健康检查与模型配置状态 |
| POST | `/api/ocr/upload` | 上传小票（成员 4） |
| GET | `/api/stats`、`/api/transactions`、`/api/budgets` | 前端直连的查询接口（成员 2） |

## 10. 部署与运行时（成员 4）

- 镜像：`python:3.11-slim` 作为运行阶段；前端构建用 `node:20-alpine` 多阶段拷贝 `dist`。
- 端口：容器内 8000，映射 `8000:8000`。
- 数据卷：`./data:/app/data`（SQLite、上传图片、日志），重建容器不丢数据。
- 环境变量：由 `docker-compose.yml` 的 `env_file: .env` 注入，仓库只提交 `.env.example`。
- 健康检查：`GET /api/health`，`healthcheck` 间隔 30s。
- 文档要求：README 中的 Docker 命令必须与实际一致，评审按文档从零执行。

## 11. 测试与质量

| 类型 | 工具 | 命令 / 范围 |
| --- | --- | --- |
| Agent 离线回归 | pytest + RuleBasedLLM + 内存业务桩 | `pytest tests --mock-llm`（30 条评测集 + 23 项契约/链路/兜底测试） |
| 真实模型评测 | pytest `--live` + LLMClient | 生成 `tests/live_report.md`，统计意图通过率 |
| 业务层单测 | pytest + 临时 SQLite | 成员 2 补齐增删改查、统计、预算边界 |
| 前端验证 | 手动验收清单 + `npm run build` | 确认卡片、图表、错误提示、响应式 |
| 代码规范 | UTF-8、命名规范、模块拆分 | 关键函数 docstring；禁止把逻辑堆进单文件 |

## 12. 版本矩阵与环境要求

| 依赖 | 版本 | 说明 |
| --- | --- | --- |
| Python | 3.11.x | 不使用 3.12+ 的新语法，避免评审环境差异 |
| Node.js | 20 LTS | 仅前端构建需要 |
| npm | 10.x | 锁文件提交 `package-lock.json` |
| Docker | 24+ / compose v2 | 容器启动完整服务 |
| SQLite | 3.40+ | 随 Python 内置，WAL 模式 |
| 浏览器 | Chrome / Edge 最新版 | 演示环境 |

## 13. 配置项清单

| 变量 | 默认值 | 归属 | 说明 |
| --- | --- | --- | --- |
| `LLM_BASE_URL` | `https://api.deepseek.com/v1` | 成员 1 | OpenAI 兼容地址 |
| `LLM_API_KEY` | 空 | 成员 1 | 不提交仓库 |
| `LLM_MODEL` | `deepseek-chat` | 成员 1 | 对话模型 |
| `VISION_MODEL` | 空 | 成员 4 | OCR/视觉模型名 |
| `DB_PATH` | `data/app.db` | 成员 2 | SQLite 路径 |
| `TIMEZONE` | `Asia/Shanghai` | 成员 1 | 相对日期换算 |
| `LLM_TIMEOUT_SECONDS` | `30` | 成员 1 | 单次请求超时 |
| `LLM_MAX_RETRIES` | `2` | 成员 1 | 重试次数 |
| `AGENT_MAX_TOOL_CALLS` | `4` | 成员 1 | 单轮工具上限 |
| `AGENT_MEMORY_WINDOW` | `8` | 成员 1 | 记忆保留原文条数 |

## 14. 分工与交付映射

| 成员 | 技术落点 | 交付物 |
| --- | --- | --- |
| 成员 1 | FastAPI + Agent 编排 + LLM 客户端 + SQLite 记忆 + pytest 评测 | `backend/app/{agent,api}`、`tests/`、契约与设计文档 |
| 成员 2 | SQLAlchemy + SQLite + 统计/预算 SQL + CSV 导入 | `backend/app/services/transaction_service.py`、建表与示例数据 |
| 成员 3 | React + TS + Vite + ECharts | `frontend/` 页面与组件、构建产物 |
| 成员 4 | 视觉模型 / PaddleOCR + Docker | `backend/app/services/ocr_service.py`、`Dockerfile`、`docker-compose.yml`、样例小票 |

## 15. 选型取舍与风险

| 决策 | 取舍 | 风险与应对 |
| --- | --- | --- |
| SQLite 而非 Postgres | 零运维、单文件便于复现 | 并发写有限；演示场景足够，必要时加写锁与 WAL |
| OpenAI 兼容协议 | 一家 SDK 切多家供应商 | 各供应商 JSON/工具调用细节有差异，已做降级与重试 |
| 视觉大模型做主 OCR | 版式鲁棒、开发快 | 费用与网络依赖；保留 PaddleOCR 兜底 |
| 不引入向量库 / RAG | 记账场景数据量小，SQL 统计即可 | 不做语义检索；后续如需可加 sqlite-vec |
| 前端产物由 FastAPI 托管 | 部署简单、无跨域 | 前后端同仓构建，镜像略大 |
| 规则模式作为无 Key 降级 | 保证任何环境可演示 | 仅覆盖固定表达，README 已注明能力边界 |
