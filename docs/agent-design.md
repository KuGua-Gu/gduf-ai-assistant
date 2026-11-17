# Agent 设计文档

本文档说明 Agent 核心的架构、关键流程与设计取舍，内容对应 `backend/app/agent/` 下的实际实现，供答辩与联调参考。

## 1. 整体架构

```text
+-------------------+         HTTP / JSON          +--------------------------------+
|   React 前端      |  ------------------------->  |  FastAPI  (app/main.py)        |
|   （成员 3）      |  <-------------------------  |  POST /api/chat                |
+-------------------+                              |  POST /api/chat/confirm        |
                                                   |  DELETE /api/chat/session/{id} |
                                                   |  GET  /api/health              |
                                                   +---------------+----------------+
                                                                   |
                                                    +--------------v---------------+
                                                    |  AgentOrchestrator            |
                                                    |  1. 越界检测                   |
                                                    |  2. 待补齐草稿处理             |
                                                    |  3. LLM + 工具调用循环         |
                                                    |  4. 确认动作执行               |
                                                    +---+-----------+-----------+---+
                                                        |           |           |
                                          Prompt / LLM <+           |           +--> MemoryStore
                                                                   |                （SQLite：会话 / 消息 / 摘要）
                                                   +---------------v----------------+
                                                   |  ToolRegistry（7 + 1 个工具）  |
                                                   |  JSON Schema 校验 + 结构化结果 |
                                                   +---------------+----------------+
                                                                   |
                                            +----------------------v----------------------+
                                            |  TransactionService（成员 2，SQLite）        |
                                            |  OcrService（成员 4）                        |
                                            +---------------------------------------------+

旁挂模块：
- Safety（app/agent/safety.py）：在进入模型前做正则越界检测，命中直接拒绝。
- MemoryStore（app/agent/memory.py）：只维护 agent_sessions / agent_messages 两张表，
  不触碰业务表；每次操作独立连接，WAL + busy_timeout。
- LLMClient（app/agent/llm_client.py）：OpenAI 兼容协议，负责重试、用量统计与 Key 脱敏。
```

组件职责：

| 组件 | 文件 | 职责 |
| --- | --- | --- |
| 应用入口 | `config.py`、`main.py` | 环境变量、CORS、路由注册、统一错误格式 |
| 装配 | `api/deps.py` | 按配置组装单例 Orchestrator，业务/OCR 未就绪时降级到桩 |
| 编排 | `agent/orchestrator.py` | 意图路由、工具循环、澄清、确认、兜底 |
| 工具 | `agent/tools.py` | 工具定义、Schema 导出、参数校验、写操作转待确认动作 |
| 模型 | `agent/llm_client.py`、`agent/mock_llm.py` | 真实模型客户端 / 离线规则模型 |
| 记忆 | `agent/memory.py` | 会话、消息、摘要压缩、临时状态 |
| 提示词 | `agent/prompts.py` | 日期与类别注入、工具/写操作/AA/风格/边界规则、澄清话术 |
| 安全 | `agent/safety.py` | 越界请求识别与拒绝话术 |
| 契约 | `agent/schemas.py`、`services/contracts.py` | 请求响应模型、业务层 Protocol |

## 2. 一次记账请求的时序

以「午饭 25」→ 用户确认 → 入账为例：

```text
前端            /api/chat        Orchestrator          LLM            ToolRegistry / 业务层
 |                  |                  |                 |                     |
 |-- message ------>|                  |                 |                     |
 |                  |-- chat() ------->|                 |                     |
 |                  |                  |-- 写入 user 消息 -> MemoryStore         |
 |                  |                  |-- 越界检测（未命中）                     |
 |                  |                  |-- 组装 system prompt + 最近 8 条上下文   |
 |                  |                  |-- chat(tools) -->|                     |
 |                  |                  |<-- tool_call: create_transactions ------|
 |                  |                  |-- 校验参数 / 归一化类别 ----------------->|
 |                  |                  |<-- PendingAction(create, draft) ---------|
 |                  |                  |-- tool message（已生成卡片）------------>|
 |                  |                  |-- chat(tools) -->|                     |
 |                  |                  |<-- 最终文案 ----------------------------|
 |<-- ChatResponse -|<-- 返回卡片 -----|                  |                     |
 |                  |                  |                 |                     |
 |-- 用户点击确认 -->|                  |                 |                     |
 |                  |-- confirm() ---->|                 |                     |
 |                  |                  |-- registry.execute("create_transactions") ->|
 |                  |                  |<-- {created:[{id,...}]} ------------------|
 |<-- created=1 ----|<-- 回复 ---------|                 |                     |
```

步骤说明：

1. 前端 `POST /api/chat`，可带 `session_id`；缺省由后端创建。
2. Orchestrator 先把用户消息写入 `agent_messages`，保证多轮上下文完整。
3. 越界检测：命中高风险表达时直接返回拒绝话术，不调用模型与工具。
4. 若会话存在未补齐草稿，优先把本轮输入当补充信息合并（换话题则放弃草稿）。
5. 正常路径组装 system prompt 与最近 8 条上下文，调用模型并携带全部工具 Schema。
6. 模型返回 `create_transactions` 工具调用；工具层做 Pydantic 参数校验、类别归一化。
7. 写操作不落库，转成 `PendingAction`，并以 `{"ok": true, "data": "已生成待确认卡片..."}` 回填模型。
8. 模型生成面向用户的文案，Orchestrator 组装 `pending_actions`、`transaction_preview`、`confirm_required=true` 返回。
9. 用户在前端点击确认，前端把 `pending_actions` 原样回传 `POST /api/chat/confirm`。
10. Orchestrator 逐条执行写工具，统计成功/失败数，成功后清空待补齐状态并返回「已入账 N 笔」。

## 3. 工具清单与设计取舍

| 工具 | 类型 | 何时执行 |
| --- | --- | --- |
| `create_transactions` | 写 | 对话阶段只生成确认卡片，confirm 时执行 |
| `update_transaction` | 写 | 同上 |
| `delete_transaction` | 写 | 同上 |
| `query_transactions` | 读 | 对话阶段直接执行，结果回填模型 |
| `get_stats` | 读 | 同上 |
| `get_budget_status` | 读 | 同上 |
| `set_budget` | 直接执行 | 对话阶段立即生效，不生成确认卡片 |
| `ocr_receipt` | 读（可选） | OCR 服务注册后可用，供模型识别小票 |

**为什么写操作只生成确认卡片，不直接落库？**

- 记账数据一旦写错，用户很难发现，尤其是指代不清的「花了点钱」「和同事吃饭」。
- 模型可能误判金额、类别或日期，确认卡片把最终决定权交还给用户，形成「模型起草、用户签字」的两阶段提交。
- 卡片同时承担可视化校对作用：金额、类别、日期、备注一目了然，缺失字段会在出卡前被追问，不会把空值写入账本。
- 代价是多一次请求（confirm），且前端必须原样回传 `pending_actions`；后端不缓存卡片，避免状态不一致。

**为什么 `set_budget` 不确认？** 它只修改预算配置，不产生账单数据，误操作的后果可由再次设置覆盖；即时生效能让「设置预算」一步完成。

其他取舍：

- Agent 只通过 `ToolRegistry` 触碰业务能力，不直接写 SQL；业务实现可替换而不改 Agent。
- 工具参数校验失败时返回结构化错误而不是抛异常，让模型有机会自我修正或转为追问。
- 修改/删除前要求模型先用 `query_transactions` 定位账单，拿不到 `transaction_id` 就说明没查到，不猜 ID。

## 4. Prompt 设计

System prompt 由 `agent/prompts.py` 的 `build_system_prompt(today, weekday)` 动态生成，包含六块内容：

1. **角色与边界**：只做记账、查账、预算与消费分析，不提供投资、贷款、法律、税务建议。
2. **日期注入**：写入「今天是 2026年11月17日（2026-11-17），星期二，时区 Asia/Shanghai」，要求所有相对时间（今天、昨天、上周三、上个月、最近 7 天）都基于该日期换算，不沿用训练数据中的日期。
3. **类别体系**：固定 9 个类别（餐饮、交通、购物、居住、娱乐、医疗、教育、人情、其他），每个类别附用途说明，要求输出类别名与之一字不差，拿不准归「其他」，明显无法判断则追问。
4. **工具优先**：涉及具体账单、金额汇总、排名必须先调用工具再回答，禁止凭记忆或猜测；多笔消费放进同一个 `transactions` 数组；时间范围换算成具体 `start_date` / `end_date`；工具返回 `ok=false` 时按 `error` 修正或如实告知。
5. **写操作措辞与禁止编造**：写工具只生成确认卡片，禁止说「已记账」「已删除」，必须说「已为你生成确认卡片」；金额、类别、日期缺失时先追问，缺一项问一项，不编造数字或字段；AA 场景只记用户实际支付金额，背景写入备注，不自行按人数相除。
6. **风格与越界**：中文口语化、正文不超过 120 字、金额保留两位小数；套现、伪造流水、规避额度、代借贷款等请求一律简短拒绝，且不调用任何写库工具。

澄清话术与兜底文案集中在同一模块：`CLARIFY_TEMPLATES` 覆盖金额、类别、日期三种缺失，`CLARIFY_LIMIT_MESSAGE` 在追问超过两轮时给出固定引导。

## 5. 异常兜底

| 类型 | 触发点 | 处理方式 | 用户看到 |
| --- | --- | --- | --- |
| 模型不可用 | 未配置 Key、鉴权失败、超时、429、5xx | `LLMClient` 对超时/连接/429/5xx 做指数退避重试（默认 2 次），仍失败抛 `LLMUnavailableError`；对话循环捕获后返回兜底话术 | 「模型服务暂时不可用，请稍等片刻再试；你也可以先在账单页手动记一笔。」 |
| JSON 解析失败 | `chat_json` 输出不是合法 JSON | 追加「请只输出 JSON 对象」的修复提示重试一次，仍失败抛 `OutputFormatError`；工具实参非法 JSON 时置 `{}`，由工具层返回 `ok=false` 让模型修正 | 请求层面返回 `OUTPUT_FORMAT_ERROR`（HTTP 500）或由模型转为追问 |
| 工具异常 | 业务层抛错、参数非法、找不到账单 | `ToolRegistry.execute` 统一捕获 `ToolExecutionError` 与其他异常，转成 `ToolResult(ok=false, error=...)` 回填模型；写操作连续 2 次参数校验失败时停止重试 | 「这条信息我反复理解有偏差，先不写入账本。你可以直接告诉我「金额 + 类别」……」 |
| 上下文超长 | 模型返回含 `context` 的错误详情 | `LLMUnavailableError` 被转换为 `ContextOverflowError`，提示开启新会话；记忆窗口压缩降低触发概率 | 「当前对话太长了，可以点「新会话」后继续，我会保留必要的记账上下文。」 |

补充：`confirm` 阶段单笔失败不会中断其他条目，最终统计 `created` / `failed`，全部失败时提示「这次没有入账成功，请检查金额、类别和日期是否完整。」

## 6. 多轮记忆

- 存储：SQLite 同一数据库文件（默认 `data/app.db`）中的 `agent_sessions` 与 `agent_messages`，不触碰业务表。
- 每次操作独立建连，开启 WAL 与 `busy_timeout=5000`，事务内提交。
- 上下文构造：`MemoryStore.context()` 返回「可选的历史摘要」+「最近 `window` 条原文」，`window` 默认 8，可通过 `AGENT_MEMORY_WINDOW` 调整。
- 摘要压缩：当消息总数超过 `window * 2`（默认 16 条）时，把最近 `window` 条之外的旧消息拼成一条摘要；单条截断 120 字，整体上限 800 字，写入 `agent_sessions.summary`。压缩不调用大模型，成本可控。
- 临时状态：待补齐草稿与追问次数存于 `agent_sessions.state_json`，确认成功、取消、换话题后清空。
- 会话清理由 `DELETE /api/chat/session/{id}` 删除该会话全部消息与状态。

## 7. 评测方案

评测集 `tests/agent_cases.json` 共 30 条，覆盖六类场景：

| 分组 | 条数 | 覆盖点 | 用例编号 |
| --- | --- | --- | --- |
| 记账 | 10 | 基础金额、相对日期、AA、多笔、绝对日期、各主要类别 | `record-01` ~ `record-10` |
| 查账 | 7 | 时间范围、分类统计、明细查询、今年累计 | `query-01` ~ `query-07` |
| 预算 | 4 | 类别预算、总额预算、余额查询、超支检查 | `budget-01` ~ `budget-04` |
| 澄清 | 4 | 缺金额、模糊金额、缺类别、有场景无金额 | `clarify-01` ~ `clarify-04` |
| 闲聊 | 2 | 问候、能力介绍 | `chat-01`、`chat-02` |
| 越界 | 3 | 规避额度、伪造流水、贷款口子 | `refuse-01` ~ `refuse-03` |

双模式：

- **mock（离线）**：`pytest tests/test_agent.py --mock-llm`。使用 `RuleBasedLLM` 与内存业务桩，不联网、不写生产库；除 30 条用例外，还覆盖确认闭环、澄清合并、追问上限、OCR 草稿、越界拒绝、模型不可用、输出格式异常、上下文超长、工具执行失败、工具调用上限、工具参数校验、记忆压缩、API 契约。当前结果 43 passed、1 skipped。离线 30 条评测集当前通过率 30/30（100%），无失败用例；真实模型通过率与失败归因以 `tests/live_report.md` 为准。
- **live（真实模型）**：`pytest tests/test_agent.py --live`。需在 `.env` 配置 Key，逐条调用真实模型，按 `expected_intent` 与 `actual_intent` 统计意图一致率，并生成 `tests/live_report.md`（含模型名、通过率、逐条明细），阈值 50%。

断言不只看意图：还会检查实际调用的工具名、草稿中的金额/类别/日期/备注/条数，以及澄清场景下缺失字段确实为 `null`（防止模型猜测）。

## 8. 已知局限

- **规则模式能力有限**：离线 `RuleBasedLLM` 依赖关键词与正则，能覆盖评测集与演示，但复杂口语、长句、多条件组合容易误判，不能替代真实模型。
- **类别关键词表**：类别识别依赖 `categories.py` 的关键词表与匹配顺序，覆盖常见消费场景；新商户、新说法可能落入「其他」，需要持续补充词表。
- **无向量记忆**：长会话只做文本拼接摘要，没有向量检索与语义召回，很久之前的细节会丢失；摘要本身也可能压缩掉关键数字。
- **并发与多用户隔离**：Orchestrator 是进程内单例，`session_id` 是唯一的会话边界，没有鉴权与用户体系；多用户共用同一数据库文件，高并发下依赖 SQLite 的 WAL 与超时设置，未做压力验证。

业务层 SQLite 与真实 OCR 服务尚待成员 2/4 按契约接入，接入后 Agent 代码无需改动。
