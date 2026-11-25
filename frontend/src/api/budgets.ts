/** 预算接口（成员 2）。 */
import { apiGet, apiPut } from './client'
import type { BudgetResponse, BudgetStatusResponse, BudgetUpsertRequest } from '../types/contract'

export function fetchBudgetStatus(month?: string): Promise<BudgetStatusResponse> {
  return apiGet<BudgetStatusResponse>('/budgets', month ? { month } : {})
}

export function upsertBudget(payload: BudgetUpsertRequest): Promise<BudgetResponse> {
  return apiPut<BudgetResponse>('/budgets', payload)
}
