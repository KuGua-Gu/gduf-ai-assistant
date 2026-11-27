/** 类别体系与展示色，需与后端 backend/app/agent/categories.py 的 CATEGORIES 保持一致。 */

export const CATEGORIES = [
  '餐饮',
  '交通',
  '购物',
  '居住',
  '娱乐',
  '医疗',
  '教育',
  '人情',
  '其他',
] as const

export type Category = (typeof CATEGORIES)[number]

/** 图表与标签配色（与整体色板一致，避免 ECharts 默认高饱和色）。 */
export const CATEGORY_COLORS: Record<string, string> = {
  餐饮: '#c56a3d',
  交通: '#2f8f79',
  购物: '#8a6bb8',
  居住: '#4b7fb5',
  娱乐: '#d29a3c',
  医疗: '#b85c6b',
  教育: '#5c8f4a',
  人情: '#a06a8f',
  其他: '#8d867e',
}

export function categoryColor(name: string, index = 0): string {
  return CATEGORY_COLORS[name] ?? ['#2f8f79', '#c56a3d', '#8a6bb8', '#4b7fb5', '#d29a3c'][index % 5]
}

/** 「总额」预算 scope 的展示名。 */
export const TOTAL_SCOPE = 'total'
export const TOTAL_SCOPE_LABEL = '总预算'

export function scopeLabel(scope: string): string {
  return scope === TOTAL_SCOPE ? TOTAL_SCOPE_LABEL : scope
}
