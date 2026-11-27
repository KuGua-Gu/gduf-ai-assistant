# 个人记账与消费分析 AI 助手

2026 GDUF 人工智能工作室二轮考核 · 方向一 · 选题 A
团队仓库：<https://github.com/KuGua-Gu/gduf-ai-assistant>

## 项目简介

用自然语言完成记账、查账和预算管理：一句「午饭 25 元」，Agent 自动解析金额、类别与日期，生成确认卡片，用户确认后才真正入账；也可以直接问「上个月吃饭花了多少」「这个月哪类花得最多」，或设置、查询月度预算。

项目同时打通了小票/支付截图链路：前端上传图片拿到 `image_id` 后随消息提交，Agent 调用 OCR 服务生成草稿，识别缺失的字段会先追问。对套现、伪造流水、代借贷款等越界请求，Agent 在进入模型前直接拒绝。

当前仓库已完成可独立运行的 **Agent 核心 + HTTP 接口契约**：未配置模型 Key 时自动降级为离线规则模式，仍然可以完整演示记账、确认、查账、预算与拒绝链路。

## 技术栈

| 层次 | 选型 |
| --- | --- |
| 语言 / 运行时 | Python 3.11 部署基线，本地已验证 3.14.2 |
| Web 框架 | FastAPI 0.115 + Uvicorn 0.34 |
| 数据校验 / 配置 | Pydantic 2.12 + pydantic-settings |
| 存储 | SQLite（Agent 会话记忆已落地；业务账单表由成员 2 接入） |
| 大模型 | OpenAI 兼容协议，可切换 DeepSeek / 智谱 GLM / 通义千问（openai SDK 1.59） |
| 测试 | pytest 8.3 |
| 前端 | React 18 + TypeScript 5 + Vite 6 + ECharts 5 + Tailwind 3 + axios（成员 3 已交付） |
| OCR | 视觉大模型（OpenAI 兼容多模态）+ 无 Key 桩兜底；上传接口 `POST /api/ocr/upload` |

## 目录结构

```text
.
├── README.md                       # 项目说明（成员 1）
├── .env.example                    # 环境变量模板（成员 1）
├── .gitignore                      # 忽略 .env / data/ / *.db 等
├── Dockerfile                      # 运行镜像（成员 4）
├── docker-compose.yml              # 一键启动与数据卷（成员 4）
├── .dockerignore                   # 构建上下文裁剪
├── backend/
│   ├── requirements.txt            # Python 依赖
│   └── app/
│       ├── main.py                 # FastAPI 入口、CORS、统一错误格式（成员 1）
│       ├── config.py               # 环境变量配置（成员 1）
│       ├── agent/                  # Agent 核心（成员 1）
│       │   ├── orchestrator.py     # 意图路由、工具循环、草稿确认、异常兜底
│       │   ├── tools.py            # 工具定义、Schema 导出、参数校验与执行
│       │   ├── llm_client.py       # OpenAI 兼容客户端、重试与用量日志
│       │   ├── mock_llm.py         # 离线规则模型（测试/无 Key 演示）
│       │   ├── memory.py           # SQLite 会话记忆与摘要压缩
│       │   ├── prompts.py          # system prompt、澄清话术
│       │   ├── safety.py           # 越界请求识别
│       │   ├── schemas.py          # 请求/响应、草稿、待确认动作
│       │   ├── categories.py       # 类别体系、金额/日期解析
│       │   └── errors.py           # 异常体系与兜底话术
│       ├── api/
│       │   ├── chat.py             # POST /api/chat、/confirm、DELETE session（成员 1）
│       │   ├── business_schemas.py # 业务 REST 请求/响应模型（成员 2）
│       │   ├── business_deps.py    # 业务 SQLite 服务依赖（成员 2）
│       │   ├── transactions.py     # 账单查询、修改、删除接口（成员 2）
│       │   ├── stats.py            # 消费统计接口（成员 2）
│       │   ├── budgets.py          # 预算设置与查询接口（成员 2）
│       │   ├── ocr.py              # 小票上传接口 POST /api/ocr/upload（成员 4）
│       │   ├── errors.py           # 业务 API 错误类型（成员 2）
│       │   └── deps.py             # Agent / 业务服务装配与降级（成员 1）
│       ├── db/
│       │   ├── __init__.py         # 业务模型导出（成员 2）
│       │   ├── models.py           # 账单与预算表结构（成员 2）
│       │   └── init_db.py          # 示例账单幂等导入命令（成员 2）
│       └── services/
│           ├── contracts.py        # TransactionService / OcrService 协议（成员 1 定义）
│           ├── transaction_service.py # SQLite 账单、统计与预算实现（成员 2）
│           ├── ocr_service.py      # 视觉模型识别 + 桩降级（成员 4）
│           └── stubs.py            # 内存业务桩、OCR 桩（成员 1，供联调）
├── backend/samples/
│   ├── demo_transactions.csv       # 示例账单数据（成员 2）
│   └── receipts/                   # 合成小票样例 + ground_truth.csv（成员 4）
├── frontend/                       # 前端工程（成员 3）
│   ├── package.json                # 依赖与脚本（dev / build / typecheck）
│   ├── vite.config.ts              # 端口 5173、/api 代理到后端、手动分包
│   ├── README.md                   # 前端启动、页面与接口对照、自测清单
│   └── src/                        # pages / components / api / types / lib / hooks
├── tests/
│   ├── conftest.py                 # --mock-llm / --live 开关
│   ├── test_agent.py               # 30 条评测集 + 链路测试
│   ├── test_contract.py            # 跨成员 API 与业务 Protocol 契约
│   ├── test_transaction_service.py # 业务持久化、统计与预算单测（成员 2）
│   ├── test_business_api.py        # 业务 REST 接口与端到端持久化测试（成员 2）
│   ├── test_seed_import.py         # 示例数据幂等导入测试（成员 2）
│   ├── test_ocr_upload.py          # 上传接口校验测试（成员 4）
│   ├── test_ocr_service.py         # 识别解析/重试/降级测试（成员 4）
│   └── agent_cases.json            # 30 条评测用例
├── scripts/
│   ├── demo_seed.py                # 示例账单导入脚本（成员 2）
│   ├── make_receipt_samples.py     # 生成合成小票与标注（成员 4）
│   ├── check_vision.py             # 视觉模型连通性自检（成员 4）
│   └── eval_ocr.py                 # OCR 准确率评测（成员 4）
└── docs/
    ├── tech-stack.md               # 项目全技术栈与版本矩阵
    ├── api-contract.md             # 接口契约（面向成员 2/3/4）
    ├── agent-design.md             # Agent 设计文档（答辩用）
    ├── agent-slides.md             # PPT 大纲与演示脚本
    ├── integration-checklist.md    # 端到端联调清单
    └── handoff-member3.md          # 成员 3 前端交接文档
```

前端页面已由成员 3 交付（`frontend/`，见 [`frontend/README.md`](frontend/README.md)）；OCR 已提供上传接口与视觉识别实现（未配置视觉模型时退回桩实现）；容器化由 `Dockerfile` 与 `docker-compose.yml` 提供。

## 环境搭建

1. 安装 Python 3.11 或更高版本，确认版本：

   ```bash
   python --version
   ```

2. 安装依赖（在仓库根目录执行）：

   ```bash
   pip install -r backend/requirements.txt
   ```

3. 复制环境变量模板并填写模型信息：

   ```bash
   cp .env.example .env
   ```

   `.env` 放在仓库根目录（也支持 `backend/.env`）。至少填写：

   | 变量 | 说明 |
   | --- | --- |
   | `LLM_API_KEY` | 模型服务的 API Key |
   | `LLM_BASE_URL` | OpenAI 兼容接口地址 |
   | `LLM_MODEL` | 模型名称 |
   | `VISION_API_KEY` | 视觉模型 Key（OCR 用；DeepSeek 文本模型不支持图片） |
   | `VISION_BASE_URL` | 视觉模型 OpenAI 兼容地址 |
   | `VISION_MODEL` | 视觉模型名，如 `glm-4v-flash`、`qwen-vl-plus` |
   | `OCR_MAX_BYTES` | 上传图片大小上限，默认 10MB |

   三家供应商可直接照抄模板中的组合：

   | 供应商 | `LLM_BASE_URL` | `LLM_MODEL` |
   | --- | --- | --- |
   | DeepSeek | `https://api.deepseek.com/v1` | `deepseek-chat` |
   | 智谱 GLM | `https://open.bigmodel.cn/api/paas/v4` | `glm-4-flash` |
   | 通义千问 | `https://dashscope.aliyuncs.com/compatible-mode/v1` | `qwen-plus` |

   其余参数（超时、重试、工具调用上限、记忆窗口）保持默认即可，含义见 `.env.example`。

## 启动

```bash
cd backend
uvicorn app.main:app --reload --port 8000
```

- 接口文档：<http://127.0.0.1:8000/docs>
- 健康检查：`GET http://127.0.0.1:8000/api/health`

未配置 `LLM_API_KEY` 时应用仍可正常启动，Agent 自动降级为离线规则模式，此时健康检查返回：

```json
{"status": "ok", "llm_configured": false, "llm_model": "deepseek-chat"}
```

运行时会自动创建 `data/` 目录与 SQLite 文件（Agent 会话记忆表与业务账单表）。

### 启动前端

需要 Node.js 20+（首次执行先安装依赖）：

```bash
cd frontend
npm install
npm run dev
```

- 页面地址：<http://localhost:5173>
- 开发服务器把 `/api` 代理到 `http://127.0.0.1:8000`，后端需先启动
- 构建产物：`npm run build` → `frontend/dist`，按 `docs/tech-stack.md` 由 FastAPI 托管
- 前端说明与自测清单：[`frontend/README.md`](frontend/README.md)

## Docker 部署（推荐交付方式）

```bash
# 1. 准备环境变量（可留空，留空时 Agent 用规则模式、OCR 用桩实现）
cp .env.example .env

# 2. 构建并启动
docker compose up --build

# 3. 验证
curl http://127.0.0.1:8000/api/health
# → {"status":"ok","llm_configured":false,...}
# 浏览器打开 http://127.0.0.1:8000/docs
```

- 端口：容器内 8000，映射 `8000:8000`；
- 数据卷：`./data:/app/data`，SQLite 与上传的小票都在里面，重建容器不丢；
- 环境变量：`docker-compose.yml` 通过 `env_file: .env` 注入，仓库只提交 `.env.example`；
- 健康检查：镜像内置 `GET /api/health` 探针（30s 间隔）。

只用 Docker、不用 compose：

```bash
docker build -t gduf-ai-assistant .
docker run -p 8000:8000 --env-file .env -v ./data:/app/data gduf-ai-assistant
```

## 初始化示例数据

示例账单位于 `backend/samples/demo_transactions.csv`，日期使用相对今天的天数偏移，
保证演示数据始终覆盖当前时间附近。进入后端目录后执行：

```bash
cd backend
python -m app.db.init_db
```

当前 Windows 虚拟环境可直接执行：

```powershell
cd backend
..\.venv\Scripts\python.exe -m app.db.init_db
```

导入器使用 CSV 中的稳定 `seed_key` 作为幂等键。重复执行相同命令时，已经导入的
示例账单会自动跳过，不会产生重复数据。首次执行预期新增 16 条：

```text
示例数据导入完成：新增 16 条，跳过 0 条，共 16 条。
```

再次执行预期：

```text
示例数据导入完成：新增 0 条，跳过 16 条，共 16 条。
```

可选参数：

| 参数 | 说明 |
| --- | --- |
| `--csv PATH` | 指定其他示例 CSV 文件 |
| `--db-path PATH` | 覆盖本次初始化使用的 SQLite 路径 |
| `--anchor-date YYYY-MM-DD` | 固定相对日期基准，便于可复现演示 |

## 小票 OCR

链路：`POST /api/ocr/upload` 上传图片 → 拿到 `image_id` → `POST /api/chat` 带上 `image_id` → Agent 生成 OCR 草稿 → 用户确认入账。

```bash
# 1. 上传（返回 image_id）
curl -X POST http://127.0.0.1:8000/api/ocr/upload -F "file=@backend/samples/receipts/receipt-01.png"

# 2. 让 Agent 识别（把上一步的 image_id 填进去）
curl -X POST http://127.0.0.1:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "识别这张小票", "image_id": "<上一步的 image_id>"}'

# 3. 确认入账（把上一步返回的 session_id 与 pending_actions 原样回传）
```

- 配置了 `VISION_API_KEY` + `VISION_MODEL` 时走视觉大模型识别；
- 未配置时自动退回 `StubOcrService`（固定样例），保证评审无 Key 也能演示完整链路；
- 识别失败（图片模糊、模型超时）会返回可读提示，不会 500。

合成样例与评测：

```bash
# 0. 配好 .env 后先验证 Key 是否可用（识别一张样例小票）
python scripts/check_vision.py

# 生成 10 张合成小票 + ground_truth.csv（仅生成时需要 pillow）
pip install pillow
python scripts/make_receipt_samples.py

# 配置 .env 后跑准确率评测（金额 ±0.01、商户包含、日期相等）
python scripts/eval_ocr.py
```

评测口径与当前结果见 [`docs/ocr-eval.md`](docs/ocr-eval.md)。

## 测试

```bash
# 离线：不联网、不写生产库，使用规则模型与内存业务桩
pytest tests/test_agent.py --mock-llm

# 跨成员契约：API 字段、错误码与业务 Protocol
pytest tests/test_contract.py --mock-llm

# OCR：上传接口与识别服务（替身客户端，不联网）
pytest tests/test_ocr_upload.py tests/test_ocr_service.py --mock-llm

# 真实模型评测：需在 .env 中配置 Key，结果写入 tests/live_report.md
pytest tests/test_agent.py --live
```

离线结果为 **88 passed, 1 skipped**（30 条评测集 + Agent/契约/兜底测试 + 8 项 SQLite 业务单测 + 6 项业务 API 测试 + 3 项示例数据导入测试 + 6 项 OCR 上传测试 + 11 项 OCR 识别测试通过；真实模型评测项按设计跳过）。`--live` 只跑 30 条评测集，按意图一致率统计并生成报告，通过率阈值 50%；最近一次 glm-4.6v 实测 30/30（100%）。

### CI 与手动 Live 评测

- 每次 push `main` 或向 `main` 提 PR，GitHub Actions 自动运行离线回归，不消耗模型额度。
- Live 评测为手动任务：仓库 **Settings → Secrets and variables → Actions** 添加 `LLM_API_KEY`（可选 `LLM_BASE_URL`、`LLM_MODEL`），然后在 **Actions → CI → Run workflow** 勾选 `live` 运行，报告作为 `live-report` 产物上传。

## 已验证功能

| 功能 | 对应测试项 | 说明 |
| --- | --- | --- |
| 文本记账草稿确认 | `record-01` ~ `record-10`、`test_confirm_flow_writes_and_query` | 一句话解析金额/类别/日期，生成确认卡片；确认后入账并可查询 |
| 多笔与 AA | `record-03`、`record-04` | 一条消息多笔生成多张卡片；AA 只记用户实际支付金额，备注写入「和同事 AA」 |
| 查账统计 | `query-01` ~ `query-07`、`test_confirm_flow_writes_and_query` | `get_stats` 汇总、`query_transactions` 明细，支持时间范围与类别 |
| 预算设置与查询 | `budget-01` ~ `budget-04` | 类别/总额预算设置，预算余额与超支检查 |
| 澄清追问 | `clarify-01` ~ `clarify-04`、`test_clarification_merges_previous_draft`、`test_clarification_limit` | 缺字段逐项追问，补充信息合并进草稿，同一字段超过两轮给出固定引导 |
| 越界拒绝 | `refuse-01` ~ `refuse-03`、`test_safety_refusal_has_no_tool_call` | 套现、伪造流水、贷款口子等请求不进入模型，直接拒绝且不产生待确认动作 |
| OCR 上传 | `test_ocr_upload.py` | 上传返回 `image_id`、扩展名/文件头/大小校验、空文件拒绝 |
| OCR 识别 | `test_ocr_service.py`、`test_ocr_draft_requires_review` | JSON/代码块解析、脏输出重试、字段规范化、模型报错降级、无 Key 退回桩、缺日期追问后出卡 |
| 多轮记忆 | `test_memory_compaction` | 超过窗口两倍自动压缩摘要，上下文保留摘要 + 最近窗口消息 |
| API 契约 | `test_api_contract` | chat → confirm → 查询 → 参数错误 422 → 清空会话全链路 |
| SQLite 业务层 | `test_transaction_service.py` | 账单原子写入、闭区间查询、三类统计、金额精度、预算 UPSERT 与状态 |
| 业务 REST API | `test_business_api.py` | 账单筛选/修改/删除、统计、预算、404/422 及 Agent 确认后端到端持久化 |
| 示例数据导入 | `test_seed_import.py` | CSV 校验、重复执行幂等、跨日期基准幂等、非法 seed_key 拒绝 |
| 异常兜底 | `test_llm_unavailable_fallback`、`test_output_format_fallback`、`test_context_overflow_fallback`、`test_tool_execution_error_fallback`、`test_tool_argument_validation`、`test_tool_call_limit` | 模型不可用/输出格式异常/上下文超长/写库失败均有可读话术；非法参数被拦截；工具调用总次数不超过 4 次 |

## 已知问题与未完成部分

- **前端待补自动化测试**：聊天、账单、统计、预算四页已实现并可联调，但尚无 Vitest/Playwright 用例，回归依赖 `frontend/README.md` 的手工清单。
- **小票上传需联调回归**：`POST /api/ocr/upload` 已就绪（见 `docs/api-contract.md`），前端已做降级提示，接口对接后需回归一次。
- **OCR 依赖外部视觉模型**：配置 `VISION_API_KEY` / `VISION_MODEL` 后走真实识别；未配置时自动退回 `StubOcrService`（固定样例，便于无 Key 演示），此时识别结果不来自上传图片。
- **Docker 镜像待验证**：`Dockerfile` / `docker-compose.yml` 已提供，`.github/workflows/docker.yml` 会在 CI 中构建并对 `/api/health`、`/api/ocr/upload` 做冒烟；本机无 Docker 环境时以 CI 结果为准。
- **live 评测需自备 Key**：`--live` 依赖 `.env` 中的真实模型配置，未配置时测试自动跳过。

## 团队分工

| 成员 | 负责模块 | 具体职责 | 交付物 |
| --- | --- | --- | --- |
| 成员 1（我） | Agent 核心 | 编排器、工具层、LLM 客户端、多轮记忆、Prompt、越界识别、异常兜底、HTTP 接口与契约定义、30 条评测集 | `backend/app/agent/*`、`backend/app/api/*`、`backend/app/main.py`、`backend/app/config.py`、`backend/app/services/contracts.py`、`tests/*`、本 README 与 `docs/*` |
| 成员 2 | 业务与数据 | 账单/预算表设计，SQLite 落库，统计与预算 SQL，实现 `TransactionService` 协议；保证确认入账、查询统计、预算状态与契约一致 | `backend/app/services/transaction_service.py`（`SqliteTransactionService`）及数据初始化逻辑 |
| 成员 3 | 前端交互 | React 聊天界面、确认卡片、账单列表与 ECharts 统计图；处理 `session_id`、`pending_actions` 回传与错误提示 | `frontend/`（工程、页面组件、`frontend/README.md`）与 `docs/handoff-member3.md` |
| 成员 4 | OCR 与工程 | 图片上传与 OCR 识别，实现 `OcrService` 协议并输出 `OcrResult`；容器化与部署、演示环境保障 | `backend/app/services/ocr_service.py`（`ReceiptOcrService`）、Dockerfile 与部署配置 |

## API 与文档

- 全技术栈与版本来：[`docs/tech-stack.md`](docs/tech-stack.md)
- 接口契约（字段表、错误码、Tool 入参、业务 Protocol）：[`docs/api-contract.md`](docs/api-contract.md)
- Agent 设计文档（架构、时序、Prompt、兜底、评测）：[`docs/agent-design.md`](docs/agent-design.md)
- 答辩 PPT 大纲与演示脚本：[`docs/agent-slides.md`](docs/agent-slides.md)
- 前端交接文档（成员 3 → 其他成员）：[`docs/handoff-member3.md`](docs/handoff-member3.md)
- OCR 评测口径与结果：[`docs/ocr-eval.md`](docs/ocr-eval.md)
- OCR 答辩提纲（3 页 PPT + 演示脚本）：[`docs/ocr-slides.md`](docs/ocr-slides.md)
- OCR 答辩 PPT（3 页，可并入团队 PPT）：[`docs/assets/ocr-slides.pptx`](docs/assets/ocr-slides.pptx)
- 在线接口文档：启动后访问 `http://127.0.0.1:8000/docs`

## 密钥安全说明

- `.env` 已写入 `.gitignore`（同时忽略 `data/`、`*.db`、`tests/live_report.md`），**不要提交**。
- 仓库只保留 `.env.example` 占位模板，其中的 `sk-your-key-here` 会被识别为未配置。
- 模型调用日志只输出脱敏后的 Key（保留前 4 位，其余以 `***` 代替），异常信息中的 Key 也会被替换。
- 若 Key 曾误提交，请立即在供应商控制台吊销并更换。
