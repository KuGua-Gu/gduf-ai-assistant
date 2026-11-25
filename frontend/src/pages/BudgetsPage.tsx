/**
 * 预算页：查询指定月份的总预算与分类预算使用状态（GET /api/budgets），
 * 设置/覆盖预算（PUT /api/budgets，同一 month+scope 覆盖）。
 * status 只能是 normal / warning / exceeded，颜色与进度条一一对应。
 */
import { useCallback, useEffect, useState } from 'react'
import type { ApiError } from '../api/client'
import { toApiError } from '../api/client'
import { fetchBudgetStatus, upsertBudget } from '../api/budgets'
import type { BudgetStatus, BudgetStatusResponse } from '../types/contract'
import { CATEGORIES, TOTAL_SCOPE, categoryColor } from '../lib/categories'
import { currentMonth, formatMoney, formatPercent } from '../lib/format'
import { EmptyState, Loading } from '../components/EmptyState'
import { ErrorBanner } from '../components/ErrorBanner'

const STATUS_META: Record<BudgetStatus, { label: string; text: string; bar: string; chip: string }> = {
  normal: { label: '正常', text: 'text-jade-700', bar: 'bg-jade-500', chip: 'bg-jade-50 text-jade-700' },
  warning: { label: '接近上限', text: 'text-amber-700', bar: 'bg-amber-500', chip: 'bg-amber-50 text-amber-700' },
  exceeded: { label: '已超支', text: 'text-clay-600', bar: 'bg-clay-500', chip: 'bg-clay-100 text-clay-600' },
}

export function BudgetsPage() {
  const [month, setMonth] = useState(currentMonth())
  const [data, setData] = useState<BudgetStatusResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<ApiError | null>(null)

  const [scope, setScope] = useState<string>(TOTAL_SCOPE)
  const [amount, setAmount] = useState('')
  const [saving, setSaving] = useState(false)
  const [formError, setFormError] = useState('')
  const [notice, setNotice] = useState('')

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const result = await fetchBudgetStatus(month)
      setData(result)
    } catch (err) {
      setError(toApiError(err))
    } finally {
      setLoading(false)
    }
  }, [month])

  useEffect(() => {
    setAmount('')
    setNotice('')
    void load()
  }, [load])

  async function submit() {
    const value = Number(amount)
    if (!Number.isFinite(value) || value <= 0) {
      setFormError('预算金额需要大于 0。')
      return
    }
    setSaving(true)
    setFormError('')
    setNotice('')
    try {
      await upsertBudget({ month, scope, amount: Number(value.toFixed(2)) })
      setNotice(`已更新 ${month} 的${scope === TOTAL_SCOPE ? '总预算' : `${scope}预算`}为 ${formatMoney(value)} 元。`)
      await load()
    } catch (err) {
      setFormError(toApiError(err).message)
    } finally {
      setSaving(false)
    }
  }

  const totalBudget = data?.total_budget ?? null
  const totalSpent = data?.total_spent ?? 0
  const remaining = totalBudget !== null ? totalBudget - totalSpent : null
  const totalRatio = totalBudget && totalBudget > 0 ? totalSpent / totalBudget : 0
  const totalStatus: BudgetStatus = totalRatio >= 1 ? 'exceeded' : totalRatio >= 0.8 ? 'warning' : 'normal'

  const categoryItems = (data?.items ?? []).filter((item) => item.scope !== TOTAL_SCOPE)

  return (
    <div className="space-y-4 px-1 pt-1 lg:px-0">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-lg font-semibold">月度预算</h1>
          <p className="text-xs text-ink/45">额度与已用金额均由后端按「月份 + 范围」聚合，超 80% 提醒、100% 超支。</p>
        </div>
        <label className="flex items-center gap-2 text-xs text-ink/50">
          月份
          <input
            type="month"
            className="input num !w-40"
            value={month}
            onChange={(e) => setMonth(e.target.value || currentMonth())}
          />
        </label>
      </header>

      {error && <ErrorBanner error={error} onRetry={() => void load()} onDismiss={() => setError(null)} />}

      {loading && !data ? (
        <Loading text="正在读取预算…" />
      ) : (
        <div className="grid gap-4 lg:grid-cols-[1.15fr_1fr]">
          {/* 总预算概览 */}
          <section className="card p-4">
            <div className="flex items-start justify-between">
              <div>
                <p className="label">总预算（元）</p>
                <p className="num mt-1 text-2xl font-semibold">
                  {totalBudget !== null ? formatMoney(totalBudget) : '未设置'}
                </p>
              </div>
              <span className={`pill ${STATUS_META[totalStatus].chip}`}>
                {totalBudget !== null ? STATUS_META[totalStatus].label : '待设置'}
              </span>
            </div>

            <div className="mt-4 space-y-2">
              <div className="flex items-end justify-between text-xs text-ink/50">
                <span>
                  已花 <span className="num text-ink/80">{formatMoney(totalSpent)}</span> 元
                </span>
                <span className={`num ${STATUS_META[totalStatus].text}`}>{formatPercent(totalRatio)}</span>
              </div>
              <div className="h-2 overflow-hidden rounded-full bg-ink/5">
                <div
                  className={`h-full rounded-full transition-all ${STATUS_META[totalStatus].bar}`}
                  style={{ width: `${Math.min(100, Math.max(2, totalRatio * 100))}%` }}
                />
              </div>
              <p className="text-[11px] text-ink/40">
                {remaining === null
                  ? '设置总预算后即可看到剩余额度。'
                  : remaining >= 0
                    ? `剩余 ${formatMoney(remaining)} 元`
                    : `已超出 ${formatMoney(Math.abs(remaining))} 元`}
              </p>
            </div>

            <div className="mt-5 border-t border-line/70 pt-4">
              <h2 className="text-sm font-semibold">分类预算</h2>
              {categoryItems.length === 0 ? (
                <div className="mt-3">
                  <EmptyState
                    title="还没有分类预算"
                    description="在右侧把范围选成某个类别（例如「餐饮」）设置额度，超支会更早被提醒。"
                    icon="◍"
                  />
                </div>
              ) : (
                <ul className="mt-3 space-y-3.5">
                  {categoryItems.map((item) => {
                    const meta = STATUS_META[item.status]
                    return (
                      <li key={item.scope}>
                        <div className="flex items-center justify-between text-xs">
                          <button
                            type="button"
                            className="flex items-center gap-2 text-ink/70 hover:text-ink"
                            onClick={() => {
                              setScope(item.scope)
                              setAmount(String(item.budget))
                              setNotice('')
                              setFormError('')
                            }}
                            title="点击可修改该类别预算"
                          >
                            <span
                              className="h-2 w-2 rounded-full"
                              style={{ backgroundColor: categoryColor(item.scope) }}
                            />
                            {item.scope}
                          </button>
                          <span className="num text-ink/80">
                            {formatMoney(item.spent)} / {formatMoney(item.budget)}
                          </span>
                        </div>
                        <div className="mt-1 flex items-center gap-2">
                          <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-ink/5">
                            <div
                              className={`h-full rounded-full ${meta.bar}`}
                              style={{ width: `${Math.min(100, Math.max(2, item.usage * 100))}%` }}
                            />
                          </div>
                          <span className={`num w-10 text-right text-[11px] ${meta.text}`}>
                            {formatPercent(item.usage)}
                          </span>
                          <span className={`pill ${meta.chip} !px-2 !py-0.5 !text-[10px]`}>{meta.label}</span>
                        </div>
                      </li>
                    )
                  })}
                </ul>
              )}
            </div>
          </section>

          {/* 设置预算 */}
          <section className="card h-fit p-4">
            <h2 className="text-sm font-semibold">设置 / 修改预算</h2>
            <p className="mt-1 text-[11px] text-ink/40">同一月份 + 同一范围重复设置时会覆盖旧额度。</p>

            <div className="mt-4 space-y-3">
              <label className="block">
                <span className="label mb-1 block">范围</span>
                <select className="input" value={scope} onChange={(e) => setScope(e.target.value)}>
                  <option value={TOTAL_SCOPE}>总预算（total）</option>
                  {CATEGORIES.map((c) => (
                    <option key={c} value={c}>
                      {c}
                    </option>
                  ))}
                </select>
              </label>
              <label className="block">
                <span className="label mb-1 block">金额（元）</span>
                <input
                  className="input num"
                  type="number"
                  min="0.01"
                  step="1"
                  inputMode="decimal"
                  placeholder="1500"
                  value={amount}
                  onChange={(e) => setAmount(e.target.value)}
                />
              </label>
              <button
                type="button"
                className="btn-primary w-full"
                disabled={saving}
                onClick={() => void submit()}
              >
                {saving ? '保存中…' : `保存 ${month} 预算`}
              </button>
              {formError && <p className="text-xs text-clay-600">{formError}</p>}
              {notice && <p className="text-xs text-jade-700">{notice}</p>}
            </div>

            <div className="mt-5 rounded-xl bg-sand/70 px-3 py-2.5 text-[11px] leading-relaxed text-ink/45">
              也可以直接在对话里说「这个月餐饮预算 1500」，预算会立即生效（不生成确认卡片）。
            </div>
          </section>
        </div>
      )}
    </div>
  )
}
