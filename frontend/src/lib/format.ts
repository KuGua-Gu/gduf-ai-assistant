/** 金额、日期与百分比格式化。业务时区固定 Asia/Shanghai，与后端一致。 */

const TZ_OFFSET_MINUTES = 8 * 60

/** 返回「今天」的 YYYY-MM-DD（按 Asia/Shanghai，避免浏览器时区漂移）。 */
export function todayISO(): string {
  const now = new Date()
  const shifted = new Date(now.getTime() + (TZ_OFFSET_MINUTES + now.getTimezoneOffset()) * 60_000)
  return shifted.toISOString().slice(0, 10)
}

/** 当前月 YYYY-MM。 */
export function currentMonth(): string {
  return todayISO().slice(0, 7)
}

/** n 天前的 YYYY-MM-DD。 */
export function daysAgoISO(days: number): string {
  const d = new Date(`${todayISO()}T00:00:00Z`)
  d.setUTCDate(d.getUTCDate() - days)
  return d.toISOString().slice(0, 10)
}

export function monthStartISO(month = currentMonth()): string {
  return `${month}-01`
}

/** 上个月的 YYYY-MM。 */
export function previousMonth(month = currentMonth()): string {
  const [year, m] = month.split('-').map(Number)
  const prev = new Date(Date.UTC(year, m - 2, 1))
  return `${prev.getUTCFullYear()}-${String(prev.getUTCMonth() + 1).padStart(2, '0')}`
}

export function monthEndISO(month = currentMonth()): string {
  const [year, m] = month.split('-').map(Number)
  const last = new Date(Date.UTC(year, m, 0))
  return last.toISOString().slice(0, 10)
}

/** 月末且不超过今天，用于「本月」查询范围。 */
export function monthToDateRange(month = currentMonth()): { start: string; end: string } {
  const start = monthStartISO(month)
  const today = todayISO()
  const end = today < start ? monthEndISO(month) : today
  return { start, end }
}

export function formatMoney(amount: number | null | undefined): string {
  if (amount === null || amount === undefined || Number.isNaN(amount)) return '—'
  return amount.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

export function formatPercent(ratio: number | null | undefined): string {
  if (ratio === null || ratio === undefined || Number.isNaN(ratio)) return '—'
  return `${Math.round(ratio * 100)}%`
}

/** 2026-11-21 → 11/21（同一年省略年份）。 */
export function formatDateShort(iso: string | null | undefined): string {
  if (!iso) return '日期待补'
  const [year, month, day] = iso.split('-')
  if (year === todayISO().slice(0, 4)) return `${Number(month)}/${Number(day)}`
  return `${year}/${Number(month)}/${Number(day)}`
}

export function formatDateFull(iso: string | null | undefined): string {
  if (!iso) return '—'
  const [year, month, day] = iso.split('-')
  return `${year}年${Number(month)}月${Number(day)}日`
}

const WEEKDAYS = ['周日', '周一', '周二', '周三', '周四', '周五', '周六']

export function weekdayOf(iso: string): string {
  const date = new Date(`${iso}T00:00:00Z`)
  return WEEKDAYS[date.getUTCDay()]
}

/** 图表 x 轴标签：日期类 key 压缩成 MM-DD / YYYY-MM。 */
export function shortBucketLabel(key: string, groupBy: 'category' | 'day' | 'month'): string {
  if (groupBy === 'day' && key.length === 10) return key.slice(5)
  if (groupBy === 'month' && key.length === 7) return key.slice(2).replace('-', '/')
  return key
}
