// 类别体系：与后端 backend/app/agent/categories.py 的 CATEGORIES 保持一致。
// 注意：该文件由成员 3 在 PR #5 中漏提交，OCR 联调时按前端调用点补齐；
// 如与前端原设计不同，请以成员 3 为准并同步修改。

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

/** 预算接口中表示「总预算」的 scope 值 */
export const TOTAL_SCOPE = 'total'

const CATEGORY_COLORS: Record<string, string> = {
  餐饮: '#f97316',
  交通: '#3b82f6',
  购物: '#ec4899',
  居住: '#8b5cf6',
  娱乐: '#06b6d4',
  医疗: '#10b981',
  教育: '#eab308',
  人情: '#ef4444',
  其他: '#94a3b8',
}

const FALLBACK_COLORS = ['#64748b', '#0ea5e9', '#a855f7', '#f59e0b', '#14b8a6', '#f43f5e']

/** 返回类别对应的图表颜色；未知类别按 index 取备用色，保证图表始终有色可用。 */
export function categoryColor(category: string, index = 0): string {
  return CATEGORY_COLORS[category] ?? FALLBACK_COLORS[index % FALLBACK_COLORS.length]
}
