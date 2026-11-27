// 日期与金额格式化工具。
// 注意：该文件由成员 3 在 PR #5 中漏提交，OCR 联调时按前端调用点补齐；
// 如与前端原设计不同，请以成员 3 为准。

const WEEKDAYS = ['周日', '周一', '周二', '周三', '周四', '周五', '周六']

function pad(value: number): string {
  return String(value).padStart(2, '0')
}

function toLocalISO(date: Date): string {
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`
}

function parseISO(value: string): Date | null {
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(value ?? '')
  if (!match) return null
  const [, y, m, d] = match
  return new Date(Number(y), Number(m) - 1, Number(d))
}

/** 今天（本地时区），格式 YYYY-MM-DD */
export function todayISO(): string {
  return toLocalISO(new Date())
}

/** 当前月份，格式 YYYY-MM */
export function currentMonth(): string {
  return todayISO().slice(0, 7)
}

/** N 天前的日期（本地时区），格式 YYYY-MM-DD */
export function daysAgoISO(days: number): string {
  const date = new Date()
  date.setDate(date.getDate() - days)
  return toLocalISO(date)
}

/** 上一个月，格式 YYYY-MM；不传参数时基于当前月 */
export function previousMonth(month: string = currentMonth()): string {
  const [year, monthNumber] = month.split('-').map(Number)
  const date = new Date(year, monthNumber - 2, 1)
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}`
}

/** 某个月对应的闭区间起止；不传参数时为「本月 1 日 ~ 今天」 */
export function monthToDateRange(month: string = currentMonth()): { start: string; end: string } {
  const start = `${month}-01`
  if (month === currentMonth()) {
    return { start, end: todayISO() }
  }
  const [year, monthNumber] = month.split('-').map(Number)
  const lastDay = new Date(year, monthNumber, 0).getDate()
  return { start, end: `${month}-${pad(lastDay)}` }
}

/** 完整日期：2026-11-08 → 2026年11月8日 */
export function formatDateFull(value: string): string {
  const date = parseISO(value)
  if (!date) return value ?? ''
  return `${date.getFullYear()}年${date.getMonth() + 1}月${date.getDate()}日`
}

/** 简短日期：2026-11-08 → 11-08 */
export function formatDateShort(value: string): string {
  const date = parseISO(value)
  if (!date) return value ?? ''
  return `${pad(date.getMonth() + 1)}-${pad(date.getDate())}`
}

/** 星期：2026-11-08 → 周日 */
export function weekdayOf(value: string): string {
  const date = parseISO(value)
  return date ? WEEKDAYS[date.getDay()] : ''
}

/** 图表横轴标签：day → 11/08，month → 11月，category/其他原样返回 */
export function shortBucketLabel(key: string, groupBy?: string): string {
  if (groupBy === 'month') {
    const match = /^(\d{4})-(\d{2})$/.exec(key ?? '')
    return match ? `${Number(match[2])}月` : key
  }
  if (groupBy === 'day') {
    const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(key ?? '')
    return match ? `${Number(match[2])}/${Number(match[3])}` : key
  }
  return key
}

/** 金额：1234.5 → 1,234.50（单位「元」由调用方拼接） */
export function formatMoney(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—'
  return Number(value).toLocaleString('zh-CN', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })
}

/** 比例：0.85 → 85%（非法值显示 —） */
export function formatPercent(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—'
  return `${(Number(value) * 100).toFixed(0)}%`
}
