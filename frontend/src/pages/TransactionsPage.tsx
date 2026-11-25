/**
 * 账单流水页：按日期/类别/关键词筛选，支持行内编辑（PATCH）与删除（DELETE）。
 * 修改时只提交实际变动的字段，迎合 PATCH 语义与后端「至少一个字段」的校验。
 */
import { useCallback, useEffect, useMemo, useState } from 'react'
import type { ApiError } from '../api/client'
import { toApiError } from '../api/client'
import { deleteTransaction, fetchTransactions, patchTransaction } from '../api/transactions'
import type { Transaction, TransactionPatch } from '../types/contract'
import { CATEGORIES, categoryColor } from '../lib/categories'
import {
  daysAgoISO,
  formatDateShort,
  formatMoney,
  monthToDateRange,
  previousMonth,
  todayISO,
  weekdayOf,
} from '../lib/format'
import { EmptyState, Loading } from '../components/EmptyState'
import { ErrorBanner } from '../components/ErrorBanner'
import { Modal } from '../components/Modal'

type RangePreset = 'thisMonth' | 'lastMonth' | 'last30' | 'all'

const SOURCE_LABELS: Record<string, string> = {
  text: '文本',
  ocr: '小票',
  manual: '手动',
}

const SOURCE_CLASSES: Record<string, string> = {
  text: 'bg-ink/5 text-ink/50',
  ocr: 'bg-jade-50 text-jade-700',
  manual: 'bg-amber-50 text-amber-700',
}

const EMPTY_EDIT = { amount: '', category: '', merchant: '', occurred_at: '', note: '' }

export function TransactionsPage() {
  const [rows, setRows] = useState<Transaction[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<ApiError | null>(null)
  const [preset, setPreset] = useState<RangePreset>('thisMonth')
  const [start, setStart] = useState(monthToDateRange().start)
  const [end, setEnd] = useState(monthToDateRange().end)
  const [category, setCategory] = useState('')
  const [keyword, setKeyword] = useState('')
  const [limit, setLimit] = useState(50)

  const [editing, setEditing] = useState<Transaction | null>(null)
  const [deleting, setDeleting] = useState<Transaction | null>(null)
  const [form, setForm] = useState(EMPTY_EDIT)
  const [saving, setSaving] = useState(false)
  const [formError, setFormError] = useState<string>('')

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await fetchTransactions({
        start_date: start || undefined,
        end_date: end || undefined,
        category: category || undefined,
        keyword: keyword.trim() || undefined,
        limit,
      })
      setRows(data.items)
    } catch (err) {
      setError(toApiError(err))
    } finally {
      setLoading(false)
    }
  }, [category, end, keyword, limit, start])

  useEffect(() => {
    void load()
  }, [load])

  const total = useMemo(() => rows.reduce((sum, row) => sum + row.amount, 0), [rows])

  function applyPreset(next: RangePreset) {
    setPreset(next)
    if (next === 'thisMonth') {
      const range = monthToDateRange()
      setStart(range.start)
      setEnd(range.end)
    } else if (next === 'lastMonth') {
      const month = previousMonth()
      setStart(`${month}-01`)
      setEnd(monthToDateRange(month).end)
    } else if (next === 'last30') {
      setStart(daysAgoISO(29))
      setEnd(todayISO())
    } else {
      setStart('')
      setEnd('')
    }
  }

  function openEdit(row: Transaction) {
    setEditing(row)
    setFormError('')
    setForm({
      amount: String(row.amount),
      category: row.category,
      merchant: row.merchant,
      occurred_at: row.occurred_at,
      note: row.note,
    })
  }

  function buildPatch(row: Transaction): TransactionPatch {
    const patch: TransactionPatch = {}
    const amount = Number(form.amount)
    if (Number.isFinite(amount) && Math.abs(amount - row.amount) > 0.001) {
      patch.amount = Number(amount.toFixed(2))
    }
    if (form.category !== row.category) patch.category = form.category
    if (form.merchant.trim() !== row.merchant) patch.merchant = form.merchant.trim()
    if (form.occurred_at !== row.occurred_at) patch.occurred_at = form.occurred_at
    if (form.note !== row.note) patch.note = form.note
    return patch
  }

  async function submitEdit() {
    if (!editing) return
    if (!form.amount || !Number.isFinite(Number(form.amount)) || Number(form.amount) <= 0) {
      setFormError('金额需要大于 0。')
      return
    }
    if (!form.occurred_at) {
      setFormError('请选择发生日期。')
      return
    }
    const patch = buildPatch(editing)
    if (Object.keys(patch).length === 0) {
      setFormError('没有检测到改动。')
      return
    }
    setSaving(true)
    setFormError('')
    try {
      const updated = await patchTransaction(editing.id, patch)
      setRows((prev) => prev.map((row) => (row.id === updated.id ? updated : row)))
      setEditing(null)
    } catch (err) {
      setFormError(toApiError(err).message)
    } finally {
      setSaving(false)
    }
  }

  async function submitDelete() {
    if (!deleting) return
    setSaving(true)
    try {
      await deleteTransaction(deleting.id)
      setRows((prev) => prev.filter((row) => row.id !== deleting.id))
      setDeleting(null)
    } catch (err) {
      setError(toApiError(err))
      setDeleting(null)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="space-y-4 px-1 pt-1 lg:px-0">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-lg font-semibold">账单流水</h1>
          <p className="text-xs text-ink/45">数据来自 SQLite 业务库；支持筛选、修改与删除。</p>
        </div>
        <button type="button" className="btn-ghost !py-1.5 !text-xs" onClick={() => void load()}>
          刷新
        </button>
      </header>

      <section className="card space-y-3 p-3.5">
        <div className="flex flex-wrap items-center gap-1.5">
          {(
            [
              ['thisMonth', '本月'],
              ['lastMonth', '上月'],
              ['last30', '近 30 天'],
              ['all', '全部'],
            ] as [RangePreset, string][]
          ).map(([key, label]) => (
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

        <div className="grid gap-2.5 sm:grid-cols-2 lg:grid-cols-5">
          <label className="block">
            <span className="label mb-1 block">开始日期</span>
            <input
              type="date"
              className="input num"
              value={start}
              onChange={(e) => {
                setStart(e.target.value)
                setPreset('all')
              }}
            />
          </label>
          <label className="block">
            <span className="label mb-1 block">结束日期</span>
            <input
              type="date"
              className="input num"
              value={end}
              onChange={(e) => {
                setEnd(e.target.value)
                setPreset('all')
              }}
            />
          </label>
          <label className="block">
            <span className="label mb-1 block">类别</span>
            <select className="input" value={category} onChange={(e) => setCategory(e.target.value)}>
              <option value="">全部类别</option>
              {CATEGORIES.map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </select>
          </label>
          <label className="block">
            <span className="label mb-1 block">关键词</span>
            <input
              className="input"
              placeholder="商户或备注"
              value={keyword}
              onChange={(e) => setKeyword(e.target.value)}
            />
          </label>
          <label className="block">
            <span className="label mb-1 block">条数上限</span>
            <select className="input" value={limit} onChange={(e) => setLimit(Number(e.target.value))}>
              {[20, 50, 100, 200].map((n) => (
                <option key={n} value={n}>
                  {n} 条
                </option>
              ))}
            </select>
          </label>
        </div>
      </section>

      {error && <ErrorBanner error={error} onRetry={() => void load()} onDismiss={() => setError(null)} />}

      <section className="card overflow-hidden">
        <div className="flex items-center justify-between border-b border-line/70 bg-sand/60 px-4 py-2.5 text-xs text-ink/50">
          <span>
            共 <span className="num font-medium text-ink/70">{rows.length}</span> 笔
          </span>
          <span>
            合计 <span className="num font-medium text-ink/80">{formatMoney(total)}</span> 元
          </span>
        </div>

        {loading ? (
          <Loading text="正在读取账单…" />
        ) : rows.length === 0 ? (
          <div className="p-4">
            <EmptyState
              title="这个范围内还没有账单"
              description="回到「对话记账」说一句「午饭 25 元」，确认后就会出现在这里。"
            />
          </div>
        ) : (
          <>
            {/* 桌面表格 */}
            <table className="hidden w-full text-sm md:table">
              <thead>
                <tr className="border-b border-line/60 text-left text-[11px] uppercase tracking-wider text-ink/40">
                  <th className="px-4 py-2 font-medium">日期</th>
                  <th className="px-4 py-2 font-medium">类别</th>
                  <th className="px-4 py-2 font-medium">商户 / 备注</th>
                  <th className="px-4 py-2 font-medium">来源</th>
                  <th className="px-4 py-2 text-right font-medium">金额</th>
                  <th className="px-4 py-2 text-right font-medium">操作</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.id} className="border-b border-line/40 last:border-0 hover:bg-sand/40">
                    <td className="num whitespace-nowrap px-4 py-2.5 text-ink/70">
                      {formatDateShort(row.occurred_at)}
                      <span className="ml-1.5 text-[11px] text-ink/30">{weekdayOf(row.occurred_at)}</span>
                    </td>
                    <td className="px-4 py-2.5">
                      <span
                        className="pill"
                        style={{
                          backgroundColor: `${categoryColor(row.category)}1a`,
                          color: categoryColor(row.category),
                        }}
                      >
                        {row.category}
                      </span>
                    </td>
                    <td className="max-w-[22rem] px-4 py-2.5">
                      <p className="truncate text-ink/80">{row.merchant || '—'}</p>
                      {row.note && <p className="truncate text-[11px] text-ink/40">{row.note}</p>}
                    </td>
                    <td className="px-4 py-2.5">
                      <span className={`pill ${SOURCE_CLASSES[row.source] ?? 'bg-ink/5 text-ink/50'}`}>
                        {SOURCE_LABELS[row.source] ?? row.source}
                      </span>
                    </td>
                    <td className="num px-4 py-2.5 text-right font-medium">{formatMoney(row.amount)}</td>
                    <td className="whitespace-nowrap px-4 py-2.5 text-right">
                      <button
                        type="button"
                        className="rounded-lg px-2 py-1 text-xs text-jade-700 hover:bg-jade-50"
                        onClick={() => openEdit(row)}
                      >
                        编辑
                      </button>
                      <button
                        type="button"
                        className="rounded-lg px-2 py-1 text-xs text-clay-600 hover:bg-clay-100"
                        onClick={() => setDeleting(row)}
                      >
                        删除
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>

            {/* 移动卡片列表 */}
            <ul className="divide-y divide-line/50 md:hidden">
              {rows.map((row) => (
                <li key={row.id} className="flex items-start justify-between gap-3 px-4 py-3">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <span
                        className="pill"
                        style={{
                          backgroundColor: `${categoryColor(row.category)}1a`,
                          color: categoryColor(row.category),
                        }}
                      >
                        {row.category}
                      </span>
                      <span className="num text-[11px] text-ink/35">{formatDateShort(row.occurred_at)}</span>
                    </div>
                    <p className="mt-1 truncate text-sm text-ink/80">{row.merchant || '—'}</p>
                    {row.note && <p className="truncate text-[11px] text-ink/40">{row.note}</p>}
                  </div>
                  <div className="shrink-0 text-right">
                    <p className="num text-sm font-medium">{formatMoney(row.amount)}</p>
                    <div className="mt-1 flex justify-end gap-1 text-[11px]">
                      <button type="button" className="text-jade-700" onClick={() => openEdit(row)}>
                        编辑
                      </button>
                      <button type="button" className="text-clay-600" onClick={() => setDeleting(row)}>
                        删除
                      </button>
                    </div>
                  </div>
                </li>
              ))}
            </ul>
          </>
        )}
      </section>

      <Modal
        open={editing !== null}
        title="修改账单"
        description={editing ? `#${editing.id} · ${formatDateShort(editing.occurred_at)}` : undefined}
        onClose={() => setEditing(null)}
        footer={
          <>
            <button type="button" className="btn-ghost" onClick={() => setEditing(null)}>
              取消
            </button>
            <button type="button" className="btn-primary" disabled={saving} onClick={() => void submitEdit()}>
              {saving ? '保存中…' : '保存修改'}
            </button>
          </>
        }
      >
        <div className="grid gap-3 sm:grid-cols-2">
          <label className="block">
            <span className="label mb-1 block">金额（元）</span>
            <input
              className="input num"
              type="number"
              min="0.01"
              step="0.01"
              value={form.amount}
              onChange={(e) => setForm({ ...form, amount: e.target.value })}
            />
          </label>
          <label className="block">
            <span className="label mb-1 block">类别</span>
            <select
              className="input"
              value={form.category}
              onChange={(e) => setForm({ ...form, category: e.target.value })}
            >
              {CATEGORIES.map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </select>
          </label>
          <label className="block">
            <span className="label mb-1 block">商户 / 场景</span>
            <input
              className="input"
              value={form.merchant}
              onChange={(e) => setForm({ ...form, merchant: e.target.value })}
            />
          </label>
          <label className="block">
            <span className="label mb-1 block">日期</span>
            <input
              className="input num"
              type="date"
              value={form.occurred_at}
              onChange={(e) => setForm({ ...form, occurred_at: e.target.value })}
            />
          </label>
          <label className="block sm:col-span-2">
            <span className="label mb-1 block">备注</span>
            <input
              className="input"
              value={form.note}
              onChange={(e) => setForm({ ...form, note: e.target.value })}
            />
          </label>
        </div>
        {formError && <p className="text-xs text-clay-600">{formError}</p>}
      </Modal>

      <Modal
        open={deleting !== null}
        title="删除这笔账单？"
        description={deleting ? `#${deleting.id} · ${deleting.category} · ${formatMoney(deleting.amount)} 元` : undefined}
        onClose={() => setDeleting(null)}
        footer={
          <>
            <button type="button" className="btn-ghost" onClick={() => setDeleting(null)}>
              再想想
            </button>
            <button type="button" className="btn-danger" disabled={saving} onClick={() => void submitDelete()}>
              {saving ? '删除中…' : '确认删除'}
            </button>
          </>
        }
      >
        <p className="text-xs text-ink/50">删除后无法恢复，统计与预算的已用金额会同步变化。</p>
      </Modal>
    </div>
  )
}
