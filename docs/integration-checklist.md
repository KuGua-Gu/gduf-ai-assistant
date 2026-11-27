# 端到端联调 Checklist

面向成员 2（业务 SQLite）、成员 3（前端）、成员 4（OCR/部署）与成员 1（Agent）的联调清单。
接口字段以 [`docs/api-contract.md`](./api-contract.md) 为唯一依据；任何字段变更先改契约再改代码。

## 0. 前置条件

- [ ] `main` 最新代码已拉取，CI 离线回归为绿
- [ ] 后端可启动：`cd backend && uvicorn app.main:app --port 8000`
- [ ] `GET http://127.0.0.1:8000/api/health` 返回 `{"status":"ok",...}`
- [ ] 离线契约测试通过：`python -m pytest tests/test_contract.py -q --mock-llm`
- [ ] 成员 2 已提交 `backend/app/services/transaction_service.py`（类名 `SqliteTransactionService`，构造参数为数据库路径）
- [ ] 成员 4 已提交 `backend/app/services/ocr_service.py`（类名 `ReceiptOcrService`）与上传方式说明
- [ ] 成员 3 已按契约完成页面字段绑定

## 1. 联调顺序与责任

| 顺序 | 链路 | 主要责任 | 依赖 |
| --- | --- | --- | --- |
| 1 | 文本记账 → 确认入账 → 重启后仍在 | 成员 2 + 成员 1 | 业务 SQLite |
| 2 | 查账 / 统计 | 成员 2 + 成员 1 | 链路 1 |
| 3 | 预算设置 / 查询 | 成员 2 + 成员 1 | 链路 1 |
| 4 | 前端完整交互 | 成员 3 | 链路 1–3 |
| 5 | OCR 小票 → 确认 | 成员 4 + 成员 1 | 真实 OCR |
| 6 | Docker 启动后复跑 | 成员 4 | 全部 |

## 2. 链路 A：文本记账

**请求**

```bash
curl.exe -X POST http://127.0.0.1:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"午饭 25"}'
```

**预期**

- `intent = "record_expense"`
- `confirm_required = true`，`pending_actions` 恰好 1 条，`action = "create"`
- `draft.amount = 25`、`draft.category = "餐饮"`、`draft.occurred_at` 为今天
- 此时**不应落库**：用 `query_transactions` 或账单页确认数量未增加

**确认**

```bash
curl.exe -X POST http://127.0.0.1:8000/api/chat/confirm \
  -H "Content-Type: application/json" \
  -d '{"session_id":"<上一步返回>","actions":<上一步的 pending_actions>}'
```

**预期**：`created = 1`、`failed = 0`、`reply` 形如「已入账 1 笔。」

**通过标准**

- [ ] 重启后端后再查，这笔仍在（证明不是 `InMemoryTransactionService`）
- [ ] 日志有 `trace_id`，且 `create_transactions` 的 `ok=True`
- [ ] 重复点击确认不会重复入账（或明确记录当前行为）

**排查点**

- `created = 0`：业务实现抛错或未注册；看日志 `trace_id` 与 `TOOL_EXECUTION_ERROR`
- 重启后数据消失：`deps.py` 仍降级到内存桩，检查 `transaction_service.py` 的导入路径与构造签名
- `pending_actions` 为空：先看 `intent` 与 `reply`，确认是澄清、越界还是离线规则未命中

## 3. 链路 B：查账 / 统计

**请求**

```bash
curl.exe -X POST http://127.0.0.1:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"这个月餐饮花了多少"}'
```

**预期**

- `intent = "query_stats"`
- 回复金额与数据库聚合一致；`get_stats` 返回 `total`、`items[].key/amount/count`
- 切换 `group_by=day|month` 时分类维度正确

**通过标准**

- [ ] 与服务层 `get_stats` 直接查询结果一致
- [ ] 时间范围为闭区间，跨月/跨年边界正确
- [ ] 类别筛选、关键词查询、`limit` 上限 200 生效

**排查点**

- 金额为 0：检查 `occurred_at` 是否为空（空日期不参与统计）
- 分类为空：检查业务层是否把 `category` 归一化或丢失
- 前端图表为空：先看 `/api/chat` 返回，再查前端字段映射

## 4. 链路 C：预算

**设置**

```bash
curl.exe -X POST http://127.0.0.1:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"这个月餐饮预算 1500"}'
```

**预期**

- `intent = "manage_budget"`，`pending_actions` 为空（预算即时生效，不弹确认卡片）
- `set_budget("餐饮", 1500, "YYYY-MM")` 返回 `month/scope/amount`

**查询**：输入「这个月餐饮预算还剩多少」，预期包含 `total_budget`、`total_spent`、`items[].usage/status`。
`status` 只能是 `normal | warning | exceeded`，阈值为 80% 与 100%。

**通过标准**

- [ ] 预算按 `month + scope` 唯一，重复设置覆盖旧值
- [ ] `spent` 只统计该月该类别
- [ ] 前端进度条/颜色与 `status` 对应

## 5. 链路 D：OCR 小票

**前置**：成员 4 已提供 `POST /api/ocr/upload`（`multipart/form-data`，字段 `file`，JPG/PNG/WEBP，默认上限 10MB），返回 `image_id`；未配置 `VISION_API_KEY` 时识别退回桩实现（固定样例）。

**请求 1：上传图片**

```bash
curl.exe -X POST http://127.0.0.1:8000/api/ocr/upload -F "file=@backend/samples/receipts/receipt-01.png"
# → {"image_id":"cf30d2f6...","filename":"cf30d2f6....png","size":19561,"content_type":"image/png"}
```

**请求 2：让 Agent 识别**

```bash
curl.exe -X POST http://127.0.0.1:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"识别这张小票","image_id":"<上一步的 image_id>"}'
```

**预期**

- 上传成功返回 32 位 `image_id`；类型/大小不合法时返回 415 / 413，错误体与契约一致
- `pending_actions[0].draft.source = "ocr"`，`confidence` 来自 `OcrResult`
- 字段缺失时先追问，`needs_review` 标出缺失字段
- 识别异常时返回可读话术，不出现 500
- 确认后 `created = 1`

**通过标准**

- [ ] 上传 1 张样例小票能拿到 `image_id`
- [ ] 真实 OCR 与桩结果可区分（商户/金额来自图片）
- [ ] 低置信度时前端提示用户核对
- [ ] `image_id` 为空或服务未注册时有降级提示

**排查点**

- 返回桩数据「沙县小吃 25 元」：`VISION_API_KEY` 未配置，或 `ReceiptOcrService` 导入失败（看启动日志 warning）
- 上传 415：扩展名不是 jpg/png/webp，或文件头不是图片
- 上传 413：超过 `OCR_MAX_BYTES`（默认 10MB）
- 上传后 chat 报「图片不存在或已过期」：`image_id` 拼错，或 `OCR_UPLOAD_DIR` 与上传时不一致
- 字段全空：检查 `OcrResult` 字段名是否与契约一致
- 日期为空：小票没印日期，走澄清让用户补充即可

## 6. 失败排查速查

| 现象 | 可能原因 | 处理 |
| --- | --- | --- |
| 503 `LLM_UNAVAILABLE` | 未配 Key、超时、限流 | 配 `.env` 或改离线模式复现 |
| 500 `OUTPUT_FORMAT_ERROR` | 模型输出非约定 JSON | 看 `trace_id` 日志，调 Prompt 或加修复重试 |
| 500 `CONTEXT_OVERFLOW` | 会话过长 | 清会话后重试 |
| `created = 0` | 业务写库失败 | 查 `TOOL_EXECUTION_ERROR` 与 SQLite 权限 |
| 前端字段 `undefined` | 契约不一致 | 跑 `test_contract.py`，对齐字段名 |
| 重启丢数据 | 仍是内存桩 | 检查 `deps.py` 是否成功导入业务实现 |
| OCR 返回固定样例 | 仍是 `StubOcrService` | 检查 `ReceiptOcrService` 导入与初始化参数 |

## 7. 联调记录

| 日期 | 链路 | 执行人 | 结果 | 证据（trace_id / 截图 / 命令输出） |
| --- | --- | --- | --- | --- |
|  | A 文本记账 |  |  |  |
|  | B 查账统计 |  |  |  |
|  | C 预算 |  |  |  |
|  | D OCR |  |  |  |
|  | 前端全流程 |  |  |  |
|  | Docker 复跑 |  |  |  |
