/**
 * 与 docs/api-contract.md 一一对应的类型定义。
 * 修改字段请先改契约（docs/api-contract.md），再同步本文件。
 */

export type Intent =
  | 'record_expense'
  | 'query_stats'
  | 'manage_budget'
  | 'confirm_action'
  | 'chitchat'
  | 'refuse'

export type TransactionSource = 'text' | 'ocr' | 'manual'

export type PendingActionType = 'create' | 'update' | 'delete'

/** 待确认的记账草稿；amount/category/occurred_at 允许为 null（由澄清流程补齐）。 */
export interface TransactionDraft {
  amount: number | null
  category: string | null
  merchant: string
  occurred_at: string | null
  note: string
  source: TransactionSource
  confidence: number
  needs_review: string[]
}

/** 确认卡片展示数据，仅用于渲染，不参与入账。 */
export interface TransactionPreview {
  amount: number | null
  category: string | null
  merchant: string
  occurred_at: string | null
  note: string
  source: string
  needs_review: string[]
}

export interface PendingAction {
  action: PendingActionType
  draft: TransactionDraft | null
  transaction_id: number | null
  patch: Record<string, unknown> | null
}

export interface ChatRequest {
  session_id?: string | null
  message: string
  image_id?: string | null
}

export interface ChatResponse {
  session_id: string
  reply: string
  intent: Intent
  pending_actions: PendingAction[]
  transaction_preview: TransactionPreview[]
  confirm_required: boolean
  trace_id: string
}

export interface ConfirmRequest {
  session_id: string
  actions: PendingAction[]
}

export interface ConfirmResponse {
  session_id: string
  created: number
  failed: number
  reply: string
  trace_id: string
}

export interface HealthResponse {
  status: string
  llm_configured: boolean
  llm_model: string
}

/** 统一错误响应体。 */
export interface ApiErrorBody {
  code: string
  message: string
  trace_id: string
}

/** GET /api/transactions 的列表项。 */
export interface Transaction {
  id: number
  amount: number
  category: string
  merchant: string
  occurred_at: string
  note: string
  source: TransactionSource
}

export interface TransactionListResponse {
  items: Transaction[]
  count: number
}

/** PATCH /api/transactions/{id}：只提交实际修改的字段。 */
export interface TransactionPatch {
  amount?: number
  category?: string
  merchant?: string
  occurred_at?: string
  note?: string
}

export interface TransactionQuery {
  start_date?: string
  end_date?: string
  category?: string
  keyword?: string
  limit?: number
}

export type StatsGroupBy = 'category' | 'day' | 'month'

export interface StatsItem {
  key: string
  amount: number
  count: number
}

export interface StatsResponse {
  start: string
  end: string
  group_by: StatsGroupBy
  total: number
  items: StatsItem[]
}

export type BudgetStatus = 'normal' | 'warning' | 'exceeded'

export interface BudgetStatusItem {
  scope: string
  budget: number
  spent: number
  usage: number
  status: BudgetStatus
}

export interface BudgetStatusResponse {
  month: string
  total_budget: number | null
  total_spent: number
  items: BudgetStatusItem[]
}

export interface BudgetUpsertRequest {
  month: string
  scope: string
  amount: number
}

export interface BudgetResponse {
  month: string
  scope: string
  amount: number
}

/** 成员 4 的 OCR 上传接口（POST /api/ocr/upload，multipart 字段名 file）。 */
export interface OcrUploadResponse {
  image_id: string
}
