/** 消费统计接口（成员 2）。 */
import { apiGet } from './client'
import type { StatsGroupBy, StatsResponse } from '../types/contract'

export interface StatsQuery {
  start_date?: string
  end_date?: string
  group_by?: StatsGroupBy
  category?: string
}

export function fetchStats(query: StatsQuery = {}): Promise<StatsResponse> {
  const params: Record<string, unknown> = {}
  if (query.start_date) params.start_date = query.start_date
  if (query.end_date) params.end_date = query.end_date
  if (query.group_by) params.group_by = query.group_by
  if (query.category) params.category = query.category
  return apiGet<StatsResponse>('/stats', params)
}
