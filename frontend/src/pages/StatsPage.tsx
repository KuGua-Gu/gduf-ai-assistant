/**
 * 消费统计页：类别占比（环形图）+ 日/月趋势（柱状图）+ 排行榜。
 * 数据全部来自 GET /api/stats，图表不做任何前端加总。
 */
import { useCallback, useEffect, useState } from 'react'
import type { ApiError } from '../api/client'
import { toApiError } from '../api/client'
import { fetchStats } from '../api/stats'
import type { StatsGroupBy, StatsResponse } from '../types/contract'
import { CATEGORIES, categoryColor } from '../lib/categories'
import {
  daysAgoISO,
  formatDateFull,
  formatMoney,
  formatPercent,
  monthToDateRange,
  previousMonth,
  todayISO,
} from '../lib/format'
import { CategoryPie } from '../components/charts/CategoryPie'
import { TrendChart } from '../components/charts/TrendChart'
import { EmptyState, Loading } from '../components/EmptyState'
import { ErrorBanner } from '../components/ErrorBanner'

type Preset = 'thisMonth' | 'lastMonth' | 'last30' | 'last90'

const PRESETS: [Preset, string][] = [
  ['thisMonth', '本月'],
  ['lastMonth', '上月'],
  ['last30', '近 30 天'],
  ['last90', '近 90 天'],
]

const GROUP_LABELS: Record<StatsGroupBy, string> = {
  category: '按类别',
  day: '按天',
  month: '按月',
}

export function StatsPage() {
  const [data, setData] = useState<StatsResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<ApiError | null>(null)
  const [preset, setPreset] = useState<Preset>('thisMonth')
  const [range, setRange] = useState(monthToDateRange())
  const [groupBy, setGroupBy] = useState<StatsGroupBy>('category')
  const [category, setCategory] = useState('')

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const result = await fetchStats({
        start_date: range.start,
        end_date: range.end,
        group_by: groupBy,
        category: category || undefined,
      })
      setData(result)
    } catch (err) {
      setError(toApiError(err))
    } finally {
      setLoading(false)
    }
  }, [category, groupBy, range.end, range.start])

  useEffect(() => {
    void load()
  }, [load])

  function applyPreset(next: Preset) {
    setPreset(next)
    if (next === 'thisMonth') {
      setRange(monthToDateRange())
    } else if (next === 'lastMonth') {
      const month = previousMonth()
      setRange({ start: `${month}-01`, end: monthToDateRange(month).end })
    } else if (next === 'last30') {
      setRange({ start: daysAgoISO(29), end: todayISO() })
    } else {
      setRange({ start: daysAgoISO(89), end: todayISO() })
    }
  }

  const items = data?.items ?? []
  const top = items[0]
  const count = items.reduce((sum, item) => sum + item.count, 0)
  const average = count > 0 ? (data?.total ?? 0) / count : 0
  const maxAmount = top?.amount ?? 0

  return (
    <div className="space-y-4 px-1 pt-1 lg:px-0">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-lg font-semibold">消费统计</h1>
          <p className="text-xs text-ink/45">
            {data ? `${formatDateFull(data.start)} — ${formatDateFull(data.end)} · 闭区间` : '统计口径由后端 SQL 聚合'}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-1.5">
          {PRESETS.map(([key, label]) => (
            <button
              key={key}
              type="button"
              onClick={() => applyPreset(key)}
              className={`rounded-full px-3 py-1 text-xs transition ${
                preset === key
                  ? 'bg-jade-600 text-white'
                  : 'border border-line bg-paper text-ink/60 hover:border-jade-300'
              }`}
            >
              {label}
            </button>
          ))}
        </div>
      </header>

      <section className="card flex flex-wrap items-end gap-3 p-3.5">
        <label className="block">
          <span className="label mb-1 block">开始日期</span>
          <input
            type="date"
            className="input num"
            value={range.start}
            onChange={(e) => setRange({ ...range, start: e.target.value })}
          />
        </label>
        <label className="block">
          <span className="label mb-1 block">结束日期</span>
          <input
            type="date"
            className="input num"
            value={range.end}
            onChange={(e) => setRange({ ...range, end: e.target.value })}
          />
        </label>
        <label className="block">
          <span className="label mb-1 block">类别筛选</span>
          <select className="input" value={category} onChange={(e) => setCategory(e.target.value)}>
            <option value="">全部类别</option>
            {CATEGORIES.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
        </label>
        <div>
          <span className="label mb-1 block">维度</span>
          <div className="flex rounded-xl border border-line bg-paper p-0.5">
            {(Object.keys(GROUP_LABELS) as StatsGroupBy[]).map((key) => (
              <button
                key={key}
                type="button"
                onClick={() => setGroupBy(key)}
                className={`rounded-lg px-3 py-1.5 text-xs transition ${
                  groupBy === key ? 'bg-jade-600 text-white' : 'text-ink/55 hover:text-ink'
                }`}
              >
                {GROUP_LABELS[key]}
              </button>
            ))}
          </div>
        </div>
      </section>

      {error && <ErrorBanner error={error} onRetry={() => void load()} onDismiss={() => setError(null)} />}

      <div className="grid gap-3 sm:grid-cols-3">
        <MetricCard label="总支出（元）" value={formatMoney(data?.total ?? 0)} accent />
        <MetricCard label="笔数" value={String(count)} />
        <MetricCard
          label={top ? `最大分类 · ${top.key}` : '最大分类'}
          value={top ? `${formatMoney(top.amount)} · ${formatPercent(maxAmount / (data?.total || 1))}` : '—'}
        />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <section className="card p-4">
          <header className="mb-2 flex items-center justify-between">
            <h2 className="text-sm font-semibold">类别占比</h2>
            <span className="text-[11px] text-ink/35">{top ? `最大 ${top.key}` : ''}</span>
          </header>
          {groupBy !== 'category' ? (
            <div className="space-y-2">
              <EmptyState
                title="切换到「按类别」查看占比"
                description="当前维度是日/月趋势，右侧图表按时间展示金额变化。"
                icon="◔"
              />
            </div>
          ) : loading && !data ? (
            <Loading />
          ) : (
            <CategoryPie items={items} total={data?.total ?? 0} />
          )}
        </section>

        <section className="card p-4">
          <header className="mb-2 flex items-center justify-between">
            <h2 className="text-sm font-semibold">{groupBy === 'category' ? '类别金额' : '时间趋势'}</h2>
            <span className="text-[11px] text-ink/35">{GROUP_LABELS[groupBy]}</span>
          </header>
          {groupBy === 'category' ? (
            <RankList items={items} total={data?.total ?? 0} loading={loading} />
          ) : loading && !data ? (
            <Loading />
          ) : (
            <TrendChart items={items} groupBy={groupBy} />
          )}
        </section>
      </div>

      <section className="card overflow-hidden">
        <header className="flex items-center justify-between border-b border-line/70 bg-sand/60 px-4 py-2.5">
          <h2 className="text-sm font-semibold">明细分组</h2>
          <span className="text-[11px] text-ink/40">平均每笔 {formatMoney(average)} 元</span>
        </header>
        {items.length === 0 ? (
          <div className="p-4">
            <EmptyState title="该范围内没有数据" description="换一个时间范围，或先记几笔账。" />
          </div>
        ) : (
          <ul className="divide-y divide-line/40">
            {items.map((item, index) => {
              const ratio = (data?.total ?? 0) > 0 ? item.amount / (data?.total ?? 1) : 0
              return (
                <li key={item.key} className="flex items-center gap-3 px-4 py-2.5">
                  <span className="num w-5 text-[11px] text-ink/30">{index + 1}</span>
                  <span className="w-16 shrink-0 text-sm text-ink/80">{item.key}</span>
                  <span className="h-1.5 flex-1 overflow-hidden rounded-full bg-ink/5">
                    <span
                      className="block h-full rounded-full"
                      style={{
                        width: `${Math.max(2, ratio * 100)}%`,
                        backgroundColor: categoryColor(item.key, index),
                      }}
                    />
                  </span>
                  <span className="num w-12 text-right text-[11px] text-ink/40">{formatPercent(ratio)}</span>
                  <span className="num w-24 text-right text-sm">{formatMoney(item.amount)}</span>
                  <span className="w-12 text-right text-[11px] text-ink/35">{item.count} 笔</span>
                </li>
              )
            })}
          </ul>
        )}
      </section>
    </div>
  )
}

function MetricCard({ label, value, accent = false }: { label: string; value: string; accent?: boolean }) {
  return (
    <div className="card px-4 py-3">
      <p className="label">{label}</p>
      <p className={`num mt-1 text-xl font-semibold ${accent ? 'text-jade-700' : 'text-ink'}`}>{value}</p>
    </div>
  )
}

function RankList({
  items,
  total,
  loading,
}: {
  items: StatsResponse['items']
  total: number
  loading: boolean
}) {
  if (loading && items.length === 0) return <Loading />
  if (items.length === 0) return <p className="py-10 text-center text-xs text-ink/35">该范围内没有支出数据</p>
  return (
    <ul className="space-y-2.5 pt-1">
      {items.map((item, index) => {
        const ratio = total > 0 ? item.amount / total : 0
        return (
          <li key={item.key}>
            <div className="flex items-center justify-between text-xs">
              <span className="flex items-center gap-2 text-ink/70">
                <span
                  className="h-2 w-2 rounded-full"
                  style={{ backgroundColor: categoryColor(item.key, index) }}
                />
                {item.key}
                <span className="text-[10px] text-ink/30">{item.count} 笔</span>
              </span>
              <span className="num text-ink/80">{formatMoney(item.amount)}</span>
            </div>
            <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-ink/5">
              <div
                className="h-full rounded-full transition-all"
                style={{
                  width: `${Math.max(2, ratio * 100)}%`,
                  backgroundColor: categoryColor(item.key, index),
                }}
              />
            </div>
          </li>
        )
      })}
    </ul>
  )
}
