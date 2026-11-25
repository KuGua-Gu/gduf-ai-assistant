/** 账单 REST 接口（成员 2）。 */
import { apiDelete, apiGet, apiPatch } from './client'
import type {
  Transaction,
  TransactionListResponse,
  TransactionPatch,
  TransactionQuery,
} from '../types/contract'

export function fetchTransactions(query: TransactionQuery = {}): Promise<TransactionListResponse> {
  const params: Record<string, unknown> = {}
  if (query.start_date) params.start_date = query.start_date
  if (query.end_date) params.end_date = query.end_date
  if (query.category) params.category = query.category
  if (query.keyword) params.keyword = query.keyword
  if (query.limit) params.limit = query.limit
  return apiGet<TransactionListResponse>('/transactions', params)
}

/** 局部修改，至少一个字段；只提交改动项。 */
export function patchTransaction(id: number, patch: TransactionPatch): Promise<Transaction> {
  return apiPatch<Transaction>(`/transactions/${id}`, patch)
}

export function deleteTransaction(id: number): Promise<{ deleted: boolean }> {
  return apiDelete<{ deleted: boolean }>(`/transactions/${id}`)
}
