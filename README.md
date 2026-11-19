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
| 语言 / 运行时 | Python 3.11 |
| Web 框架 | FastAPI 0.115 + Uvicorn 0.34 |
| 数据校验 / 配置 | Pydantic 2.10 + pydantic-settings |
| 存储 | SQLite（Agent 会话记忆已落地；业务账单表由成员 2 接入） |
| 大模型 | OpenAI 兼容协议，可切换 DeepSeek / 智谱 GLM / 通义千问（openai SDK 1.59） |
| 测试 | pytest 8.3 |
| 前端 | React + ECharts（成员 3 实现，尚未开始） |
| OCR | 成员 4 实现（当前为桩实现） |

## 目录结构

```text
.
├── README.md                       # 项目说明（成员 1）
├── .env.example                    # 环境变量模板（成员 1）
├── .gitignore                      # 忽略 .env / data/ / *.db 等
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
│       │   └── deps.py             # Agent / 业务服务装配与降级（成员 1）
│       └── services/
│           ├── contracts.py        # TransactionService / OcrService 协议（成员 1 定义）
│           └── stubs.py            # 内存业务桩、OCR 桩（成员 1，供联调）
├── tests/
│   ├── conftest.py                 # --mock-llm / --live 开关
│   ├── test_agent.py               # 30 条评测集 + 链路测试
│   └── agent_cases.json            # 30 条评测用例
└── docs/
    ├── tech-stack.md               # 项目全技术栈与版本矩阵
    ├── api-contract.md             # 接口契约（面向成员 2/3/4）
    ├── agent-design.md             # Agent 设计文档（答辩用）
    └── agent-slides.md             # PPT 大纲与演示脚本
```

业务层 SQLite 实现、前端页面与真实 OCR 服务尚未提交，对应文件由成员 2/3/4 按 `docs/api-contract.md` 的契约补齐。

## 环境搭建

1. 安装 Python 3.11，确认版本：

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

运行时会自动创建 `data/` 目录与 SQLite 文件（Agent 会话记忆表）。

## 测试

```bash
# 离线：不联网、不写生产库，使用规则模型与内存业务桩
pytest tests/test_agent.py --mock-llm

# 跨成员契约：API 字段、错误码与业务 Protocol
pytest tests/test_contract.py --mock-llm

# 真实模型评测：需在 .env 中配置 Key，结果写入 tests/live_report.md
pytest tests/test_agent.py --live
```

离线结果为 **53 passed, 2 skipped**（30 条评测集 + 23 项契约/链路/兜底测试通过；真实模型评测项与成员 2 业务实现项按设计跳过）。`--live` 只跑 30 条评测集，按意图一致率统计并生成报告，通过率阈值 50%；最近一次 glm-4.6v 实测 30/30（100%）。

## 已验证功能

| 功能 | 对应测试项 | 说明 |
| --- | --- | --- |
| 文本记账草稿确认 | `record-01` ~ `record-10`、`test_confirm_flow_writes_and_query` | 一句话解析金额/类别/日期，生成确认卡片；确认后入账并可查询 |
| 多笔与 AA | `record-03`、`record-04` | 一条消息多笔生成多张卡片；AA 只记用户实际支付金额，备注写入「和同事 AA」 |
| 查账统计 | `query-01` ~ `query-07`、`test_confirm_flow_writes_and_query` | `get_stats` 汇总、`query_transactions` 明细，支持时间范围与类别 |
| 预算设置与查询 | `budget-01` ~ `budget-04` | 类别/总额预算设置，预算余额与超支检查 |
| 澄清追问 | `clarify-01` ~ `clarify-04`、`test_clarification_merges_previous_draft`、`test_clarification_limit` | 缺字段逐项追问，补充信息合并进草稿，同一字段超过两轮给出固定引导 |
| 越界拒绝 | `refuse-01` ~ `refuse-03`、`test_safety_refusal_has_no_tool_call` | 套现、伪造流水、贷款口子等请求不进入模型，直接拒绝且不产生待确认动作 |
| OCR 桩链路 | `test_ocr_draft_requires_review` | 图片走 OCR 生成草稿，缺日期时追问，补充后出卡并标记来源为 `ocr` |
| 多轮记忆 | `test_memory_compaction` | 超过窗口两倍自动压缩摘要，上下文保留摘要 + 最近窗口消息 |
| API 契约 | `test_api_contract` | chat → confirm → 查询 → 参数错误 422 → 清空会话全链路 |
| 异常兜底 | `test_llm_unavailable_fallback`、`test_output_format_fallback`、`test_context_overflow_fallback`、`test_tool_execution_error_fallback`、`test_tool_argument_validation`、`test_tool_call_limit` | 模型不可用/输出格式异常/上下文超长/写库失败均有可读话术；非法参数被拦截；工具调用总次数不超过 4 次 |

## 已知问题与未完成部分

- **业务层 SQLite 未接入**：`app/api/deps.py` 会优先加载 `app.services.transaction_service.SqliteTransactionService`，该模块尚未提交，运行时自动降级为内存桩，重启后账单数据丢失。
- **前端页面未开始**：聊天界面、确认卡片、统计图表（React + ECharts）尚未实现，目前只能通过 HTTP 接口或 Swagger 联调。
- **真实 OCR 未接入**：`StubOcrService` 固定返回样例小票（沙县小吃 25.00 元），尚未对接真实识别服务与图片上传。
- **Dockerfile 未完成**：仓库暂无容器化配置，当前仅支持本地 Python 运行。
- **live 评测需自备 Key**：`--live` 依赖 `.env` 中的真实模型配置，未配置时测试自动跳过。

## 团队分工

| 成员 | 负责模块 | 具体职责 | 交付物 |
| --- | --- | --- | --- |
| 成员 1（我） | Agent 核心 | 编排器、工具层、LLM 客户端、多轮记忆、Prompt、越界识别、异常兜底、HTTP 接口与契约定义、30 条评测集 | `backend/app/agent/*`、`backend/app/api/*`、`backend/app/main.py`、`backend/app/config.py`、`backend/app/services/contracts.py`、`tests/*`、本 README 与 `docs/*` |
| 成员 2 | 业务与数据 | 账单/预算表设计，SQLite 落库，统计与预算 SQL，实现 `TransactionService` 协议；保证确认入账、查询统计、预算状态与契约一致 | `backend/app/services/transaction_service.py`（`SqliteTransactionService`）及数据初始化逻辑 |
| 成员 3 | 前端交互 | React 聊天界面、确认卡片、账单列表与 ECharts 统计图；处理 `session_id`、`pending_actions` 回传与错误提示 | 前端工程与页面组件 |
| 成员 4 | OCR 与工程 | 图片上传与 OCR 识别，实现 `OcrService` 协议并输出 `OcrResult`；容器化与部署、演示环境保障 | `backend/app/services/ocr_service.py`（`ReceiptOcrService`）、Dockerfile 与部署配置 |

## API 与文档

- 全技术栈与版本来：[`docs/tech-stack.md`](docs/tech-stack.md)
- 接口契约（字段表、错误码、Tool 入参、业务 Protocol）：[`docs/api-contract.md`](docs/api-contract.md)
- Agent 设计文档（架构、时序、Prompt、兜底、评测）：[`docs/agent-design.md`](docs/agent-design.md)
- 答辩 PPT 大纲与演示脚本：[`docs/agent-slides.md`](docs/agent-slides.md)
- 在线接口文档：启动后访问 `http://127.0.0.1:8000/docs`

## 密钥安全说明

- `.env` 已写入 `.gitignore`（同时忽略 `data/`、`*.db`、`tests/live_report.md`），**不要提交**。
- 仓库只保留 `.env.example` 占位模板，其中的 `sk-your-key-here` 会被识别为未配置。
- 模型调用日志只输出脱敏后的 Key（保留前 4 位，其余以 `***` 代替），异常信息中的 Key 也会被替换。
- 若 Key 曾误提交，请立即在供应商控制台吊销并更换。
