# 接口契约

面向成员 2（业务与数据）、成员 3（前端交互）、成员 4（OCR 与工程）。所有字段以 `backend/app/agent/schemas.py`、`backend/app/api/chat.py`、`backend/app/main.py` 的实际实现为准。

## 通用约定

- 服务地址：本地默认 `http://127.0.0.1:8000`。
- 请求与响应均为 `application/json`，UTF-8。
- 会话由 `session_id` 标识：请求不传时后端用 `uuid4().hex` 创建，并在响应中返回；前端应保存并复用。
- 每个成功响应都带 `trace_id`（12 位十六进制），报错排查时请一并提供。
- 统一错误响应体：

```json
{"code": "VALIDATION_ERROR", "message": "请求参数不合法，请检查后重试。", "trace_id": "a1b2c3d4e5f6"}
```

## 接口总览

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| POST | `/api/chat` | 发送一条对话消息（文本或图片） |
| POST | `/api/chat/confirm` | 用户确认卡片后真正入账 |
| DELETE | `/api/chat/session/{session_id}` | 清空会话（「新会话」按钮） |
| GET | `/api/health` | 健康检查与模型配置状态 |

---

## POST /api/chat

请求体 `ChatRequest`：

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `session_id` | string \| null | 否 | 前端生成的会话 ID；缺省由后端创建 |
| `message` | string | 是 | 用户输入，长度 1~2000 |
| `image_id` | string \| null | 否 | 已上传小票/截图在 OCR 服务中的 ID |

响应体 `ChatResponse`：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `session_id` | string | 会话 ID，后续请求需回传 |
| `reply` | string | 助手回复文本，前端直接展示 |
| `intent` | string | 意图枚举，见下表 |
| `pending_actions` | array | 待确认动作；为空数组表示本轮无需确认 |
| `transaction_preview` | array | 确认卡片展示数据，来自 `pending_actions` 中带草稿的 create 动作 |
| `confirm_required` | bool | 为 `true` 时前端必须展示「确认」按钮 |
| `trace_id` | string | 本次请求追踪 ID |

`intent` 取值：

| 值 | 含义 |
| --- | --- |
| `record_expense` | 记账（含草稿待确认、澄清追问） |
| `query_stats` | 查账 / 统计 |
| `manage_budget` | 设置或查询预算 |
| `confirm_action` | 修改 / 删除类待确认动作，或用户主动说「确认」 |
| `chitchat` | 闲聊、能力介绍、兜底回复 |
| `refuse` | 越界请求被拒绝 |

`pending_actions` 元素 `PendingAction`：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `action` | string | `create` / `update` / `delete`，默认 `create` |
| `draft` | object \| null | 新增账单的草稿 `TransactionDraft`；`update` / `delete` 时为 `null` |
| `transaction_id` | int \| null | 修改 / 删除的目标账单 ID；新增时为 `null` |
| `patch` | object \| null | 修改字段，可含 `amount` / `category` / `merchant` / `occurred_at` / `note` |

`draft`（`TransactionDraft`）：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `amount` | number \| null | 金额（元），未知为 `null` |
| `category` | string \| null | 消费类别，未知为 `null` |
| `merchant` | string | 商户 / 场景描述，默认空串 |
| `occurred_at` | string(date) \| null | 发生日期 `YYYY-MM-DD`，未知为 `null` |
| `note` | string | 备注，如「和同事 AA」 |
| `source` | string | `text` / `ocr` / `manual` |
| `confidence` | number | 置信度 0~1 |
| `needs_review` | string[] | 需要用户确认或修正的字段名 |

`transaction_preview` 元素 `TransactionPreview`：`amount`、`category`、`merchant`、`occurred_at`、`note`、`source`、`needs_review`，含义与草稿一致，仅供展示，不参与入账。

关键约定：

- `confirm_required = true` 时，前端应把 `pending_actions` **原样**保存并在用户点击确认时回传；后端不缓存卡片内容。
- 卡片中的「金额待补 / 类别待补 / 日期待补」表示字段缺失，此类草稿不会出现在确认卡片里，而是先走澄清追问。
- `transaction_preview` 只对应带 `draft` 的动作（当前实际只有 `create`）；修改 / 删除请直接读 `pending_actions` 的 `transaction_id` 与 `patch`。

---

## POST /api/chat/confirm

请求体 `ConfirmRequest`：

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `session_id` | string | 是 | 上一条响应返回的会话 ID |
| `actions` | array | 是 | 至少 1 个 `PendingAction`，内容来自上一条响应的 `pending_actions` |

响应体 `ConfirmResponse`：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `session_id` | string | 会话 ID |
| `created` | int | 成功入账 / 修改 / 删除的条数 |
| `failed` | int | 失败条数 |
| `reply` | string | 结果话术；成功时形如「已入账 1 笔。」，全部失败时为固定提示 |
| `trace_id` | string | 本次请求追踪 ID |

行为说明：

- `create` 要求 `draft` 的 `amount`、`category`、`occurred_at` 齐全，否则计为失败。
- `update` / `delete` 要求提供 `transaction_id`。
- 至少成功 1 条时清空该会话的待补齐草稿状态；全部失败时保留提示，用户可重新确认。
- 入账动作通过工具层 `create_transactions` / `update_transaction` / `delete_transaction` 执行，与对话阶段使用同一套参数校验。

---

## DELETE /api/chat/session/{session_id}

清除会话记录（含消息、摘要与待补齐草稿）。响应：

```json
{"cleared": true}
```

该接口不校验会话是否存在，重复调用同样返回 `true`。

---

## GET /api/health

响应：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `status` | string | 固定 `ok` |
| `llm_configured` | bool | 是否配置了可用 `LLM_API_KEY`（占位值 `sk-your...` 视为未配置） |
| `llm_model` | string | 当前配置的模型名，默认 `deepseek-chat` |

`llm_configured = false` 时 Agent 运行在离线规则模式，接口仍可用，但理解能力有限。

---

## 错误码

统一错误体为 `{"code","message","trace_id"}`，由 `backend/app/main.py` 的异常处理器生成。

| code | HTTP 状态码 | 触发场景 | 返回给用户的 message |
| --- | --- | --- | --- |
| `VALIDATION_ERROR` | 422 | 请求体缺字段、`message` 为空或超长、`actions` 为空 | 请求参数不合法，请检查后重试。 |
| `LLM_UNAVAILABLE` | 503 | 未配置 Key、鉴权/参数错误、超时、限流或 5xx 重试耗尽 | 模型服务暂时不可用，请稍等片刻再试；你也可以先在账单页手动记一笔。 |
| `OUTPUT_FORMAT_ERROR` | 500 | 模型输出无法解析为约定 JSON（`chat_json` 修复重试后仍失败） | 刚才没有理解清楚，可以换成「午饭 25 元」这样的说法再发一次吗？ |
| `TOOL_EXECUTION_ERROR` | 500 | 工具执行抛错（异常映射预留；当前工具层已就地转为 `ok=false` 结果） | 数据读写没有成功，这笔记录还没有保存，请稍后重试。 |
| `CONTEXT_OVERFLOW` | 500 | 模型报上下文超长（由 `LLM_UNAVAILABLE` 的错误详情含 `context` 转换而来） | 当前对话太长了，可以点「新会话」后继续，我会保留必要的记账上下文。 |
| `SAFETY_VIOLATION` | 500 | 异常体系预留码 | 这类请求我无法协助。 |
| `AGENT_ERROR` | 500 | 其他未细分的 Agent 异常（基类默认码） | 我这边出了点小问题，请稍后再试一次。 |

补充：

- 越界请求（套现、伪造流水、代借贷款等）当前**不抛异常**，而是正常返回 `200`，`intent = "refuse"`，`pending_actions` 为空；`SAFETY_VIOLATION` 仅作为异常体系预留。
- 工具参数非法不会产生 500：`ToolRegistry.execute` 返回 `{"ok": false, "error": ...}`，由模型决定追问或修正。

---

## image_id → OCR 流程

1. 前端先把小票/支付截图上传到 OCR 服务（成员 4 提供），拿到 `image_id`。本仓库不提供图片上传接口。
2. 调用 `POST /api/chat`，请求带 `image_id`，`message` 可写「识别这张小票」等说明。
3. Orchestrator 在进入模型前直接调用 `OcrService.recognize(image_id)`。
4. 识别结果转成 `TransactionDraft`：
   - `amount`、`merchant`、`occurred_at` 取识别值；
   - `category` 由商户名走关键词表推断；
   - `note` 取本轮 `message`；
   - `source = "ocr"`，`confidence` 取识别置信度；
   - 缺失字段写入 `needs_review`。
5. 字段齐全：返回 `pending_actions` 与 `transaction_preview`（`source = "ocr"`），等待确认。
6. 字段缺失：先追问（例如「这笔是哪天花的？」），用户补充后合并草稿再出卡。
7. OCR 调用异常：返回可读提示「这张图片暂时识别不了，可以手动告诉我金额和商户。」，不抛 500。
8. OCR 服务未注册（`ocr is None`）：提示「图片识别能力暂未接入，可以先手动告诉我金额和类别。」。
9. 当前桩实现 `StubOcrService` 固定返回：金额 25.00、商户「沙县小吃」、日期今天、置信度 0.72。
10. 工具 `ocr_receipt` 供模型在纯文本链路显式调用；HTTP 的 `image_id` 路径不经过模型。

---

## 业务层 Protocol

成员 2 实现 `TransactionService`，成员 4 实现 `OcrService`，定义在 `backend/app/services/contracts.py`。`app/api/deps.py` 会优先导入 `app.services.transaction_service.SqliteTransactionService` 与 `app.services.ocr_service.ReceiptOcrService`，导入失败时自动降级为 `stubs.py` 中的桩实现。

### TransactionService

| 方法 | 签名 | 返回结构 |
| --- | --- | --- |
| `create_transactions` | `(drafts: Sequence[TransactionDraft], session_id: str \| None = None)` | `list[dict]`：每笔落库结果，至少包含 `id`、`amount`、`category` |
| `update_transaction` | `(transaction_id: int, patch: dict[str, Any])` | `dict \| None`：更新后的账单；找不到返回 `None` |
| `delete_transaction` | `(transaction_id: int)` | `bool`：是否删除成功 |
| `query_transactions` | `(filters: TransactionFilter)` | `list[dict]`：账单列表（桩实现字段：`id`、`amount`、`category`、`merchant`、`occurred_at`、`note`、`source`） |
| `get_stats` | `(start: date, end: date, group_by: str = "category", category: str \| None = None)` | `{"start","end","group_by","total","items":[{"key","amount","count"}]}` |
| `set_budget` | `(scope: str, amount: float, month: str)` | `dict`：写入后的预算信息（桩实现：`{"month","scope","amount"}`） |
| `get_budget_status` | `(month: str)` | `{"month","total_budget","total_spent","items":[{"scope","budget","spent","usage","status"}]}` |

约定：

- `scope` 为 `"total"`（总额）或类别名；`month` 为 `YYYY-MM`。
- `get_budget_status` 的 `status` 取值 `normal` / `warning` / `exceeded`，`usage` 为已用比例（`spent / budget`）。
- `get_stats` 的 `group_by` 取 `category` / `day` / `month`，`items` 按金额倒序。
- 时间范围均为闭区间；`query_transactions` 的 `limit` 默认 50、上限 200。

### OcrService

| 方法 | 签名 | 返回结构 |
| --- | --- | --- |
| `recognize` | `(image_id: str)` | `OcrResult`：`amount: float \| None`、`merchant: str`、`occurred_at: date \| None`、`confidence: float(0~1)`、`raw: dict` |

---

## Agent 侧工具清单

工具注册在 `backend/app/agent/tools.py`，共 7 个核心工具；OCR 服务可用时追加第 8 个 `ocr_receipt`。

| 工具名 | 类型 | 入参字段 | 用途 |
| --- | --- | --- | --- |
| `create_transactions` | 写（需确认） | `transactions`: 数组，至少 1 条，元素为 `TransactionDraft` | 新增记账，多笔消费放同一数组 |
| `update_transaction` | 写（需确认） | `transaction_id`: int ≥ 1；`patch`: object（`amount`/`category`/`merchant`/`occurred_at`/`note`） | 修改已有账单 |
| `delete_transaction` | 写（需确认） | `transaction_id`: int ≥ 1 | 删除账单 |
| `query_transactions` | 读 | `start_date`、`end_date`、`category`、`keyword`、`limit`（1~200，默认 50） | 查账单明细 |
| `get_stats` | 读 | `start_date`（缺省本月 1 日）、`end_date`（缺省今天）、`group_by`（`category`/`day`/`month`，默认 `category`）、`category` | 金额汇总与分类排名 |
| `set_budget` | 直接执行 | `scope`（`total` 或类别名）、`amount`（> 0）、`month`（`YYYY-MM`，缺省本月） | 设置月度预算 |
| `get_budget_status` | 读 | `month`（`YYYY-MM`，缺省本月） | 查询预算使用情况 |
| `ocr_receipt` | 读（可选注册） | `image_id`: string，非空 | 识别小票，返回金额/商户/日期/置信度 |

说明：

- 三个账单写工具在对话阶段不落库，只转成 `PendingAction`；只有 `/api/chat/confirm` 会真正执行。
- `set_budget` 的 `write_action` 为 `None`，设置后立即生效，不生成确认卡片。
- 工具参数校验失败时返回 `{"ok": false, "error": "参数校验失败：..."}`，由模型修正或追问。

---

## 请求示例（chat → confirm）

### 1. 生成确认卡片

```bash
curl -X POST http://127.0.0.1:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "午饭 25"}'
```

响应示例（日期与 `session_id` 以实际返回为准）：

```json
{
  "session_id": "3f9c2a7d8b1e4c6fa5d0e9b7c1a24365",
  "reply": "已为你生成 1 张确认卡片：餐饮 25.00 元（11月17日）。确认后才会入账。",
  "intent": "record_expense",
  "pending_actions": [
    {
      "action": "create",
      "draft": {
        "amount": 25.0,
        "category": "餐饮",
        "merchant": "午饭",
        "occurred_at": "2026-11-17",
        "note": "",
        "source": "text",
        "confidence": 1.0,
        "needs_review": []
      },
      "transaction_id": null,
      "patch": null
    }
  ],
  "transaction_preview": [
    {
      "amount": 25.0,
      "category": "餐饮",
      "merchant": "午饭",
      "occurred_at": "2026-11-17",
      "note": "",
      "source": "text",
      "needs_review": []
    }
  ],
  "confirm_required": true,
  "trace_id": "a1b2c3d4e5f6"
}
```

### 2. 确认入账

把上一步的 `session_id` 与 `pending_actions` 原样回传：

```bash
curl -X POST http://127.0.0.1:8000/api/chat/confirm \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "3f9c2a7d8b1e4c6fa5d0e9b7c1a24365",
    "actions": [
      {
        "action": "create",
        "draft": {
          "amount": 25.0,
          "category": "餐饮",
          "merchant": "午饭",
          "occurred_at": "2026-11-17",
          "note": "",
          "source": "text",
          "confidence": 1.0,
          "needs_review": []
        },
        "transaction_id": null,
        "patch": null
      }
    ]
  }'
```

响应：

```json
{
  "session_id": "3f9c2a7d8b1e4c6fa5d0e9b7c1a24365",
  "created": 1,
  "failed": 0,
  "reply": "已入账 1 笔。",
  "trace_id": "0f9e8d7c6b5a"
}
```

> Windows PowerShell 中 `curl` 是 `Invoke-WebRequest` 的别名，请改用 `curl.exe`，或用 `Invoke-RestMethod -Method Post -ContentType 'application/json' -Body '...'`。
