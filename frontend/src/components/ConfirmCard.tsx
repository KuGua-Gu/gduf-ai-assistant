/**
 * 确认卡片：create 可编辑金额/类别/商户/日期/备注；
 * update 可编辑 patch 内的字段；delete 只展示目标账单。
 * 确认时把改动写回 `PendingAction`，其余字段（source/confidence/needs_review）原样保留，
 * 保证回传给 /api/chat/confirm 的结构与契约一致。
 */
import { useEffect, useMemo, useState } from 'react'
import type { PendingAction, TransactionDraft } from '../types/contract'
import { CATEGORIES } from '../lib/categories'
import { formatMoney } from '../lib/format'

export type CardStatus = 'pending' | 'submitting' | 'confirmed' | 'failed'

interface ConfirmCardProps {
  action: PendingAction
  index: number
  status: CardStatus
  onConfirm: (action: PendingAction) => void
}

const FIELD_LABELS: Record<string, string> = {
  amount: '金额',
  category: '类别',
  merchant: '商户',
  occurred_at: '日期',
  note: '备注',
}

const SOURCE_LABELS: Record<string, string> = {
  text: '文本',
  ocr: '小票识别',
  manual: '手动',
}

export function ConfirmCard({ action, index, status, onConfirm }: ConfirmCardProps) {
  const draft = action.draft
  const patch = action.patch ?? {}

  const initial = useMemo(() => {
    const source = (draft ?? patch) as Record<string, unknown> | undefined
    return {
      amount: source?.amount === null || source?.amount === undefined ? '' : String(source.amount),
      category: (source?.category as string | undefined) ?? '',
      merchant: (source?.merchant as string | undefined) ?? '',
      occurred_at: (source?.occurred_at as string | undefined) ?? '',
      note: (source?.note as string | undefined) ?? '',
    }
  }, [action])

  const [form, setForm] = useState(initial)

  useEffect(() => {
    setForm(initial)
  }, [initial])

  const locked = status !== 'pending'
  const isCreate = action.action === 'create'
  const amountValue = Number(form.amount)
  const amountValid = form.amount !== '' && Number.isFinite(amountValue) && amountValue > 0
  const categoryValid = form.category.trim().length > 0
  const dateValid = form.occurred_at.length === 10
  const valid = isCreate
    ? amountValid && categoryValid && dateValid
    : action.action === 'update'
      ? Object.keys(patch).length > 0
      : true

  const needsReview = draft?.needs_review ?? []
  const lowConfidence = (draft?.confidence ?? 1) < 0.8 || needsReview.length > 0

  function update(key: keyof typeof form, value: string) {
    setForm((prev) => ({ ...prev, [key]: value }))
  }

  function buildAction(): PendingAction {
    if (isCreate && draft) {
      const nextDraft: TransactionDraft = {
        ...draft,
        amount: Number.isFinite(amountValue) ? Number(amountValue.toFixed(2)) : draft.amount,
        category: form.category.trim() || draft.category,
        merchant: form.merchant.trim(),
        occurred_at: form.occurred_at || draft.occurred_at,
        note: form.note,
      }
      return { ...action, draft: nextDraft }
    }
    if (action.action === 'update') {
      const nextPatch: Record<string, unknown> = { ...patch }
      if ('amount' in patch) nextPatch.amount = Number.isFinite(amountValue) ? Number(amountValue.toFixed(2)) : patch.amount
      if ('category' in patch) nextPatch.category = form.category.trim() || patch.category
      if ('merchant' in patch) nextPatch.merchant = form.merchant.trim()
      if ('occurred_at' in patch) nextPatch.occurred_at = form.occurred_at || patch.occurred_at
      if ('note' in patch) nextPatch.note = form.note
      return { ...action, patch: nextPatch }
    }
    return action
  }

  const title = isCreate
    ? '记账确认'
    : action.action === 'update'
      ? '修改账单确认'
      : '删除账单确认'

  const statusBadge = {
    pending: null,
    submitting: <span className="pill bg-ink/5 text-ink/50">提交中…</span>,
    confirmed: <span className="pill bg-jade-50 text-jade-700">✓ 已入账</span>,
    failed: <span className="pill bg-clay-100 text-clay-600">未成功</span>,
  }[status]

  return (
    <article
      className={`card animate-rise overflow-hidden ${locked && status === 'confirmed' ? 'opacity-75' : ''}`}
      aria-label={`${title} ${index + 1}`}
    >
      <header className="flex items-center justify-between gap-2 border-b border-line/70 bg-sand/60 px-4 py-2.5">
        <div className="flex items-center gap-2">
          <span className="num text-[11px] text-ink/35">#{index + 1}</span>
          <h3 className="text-sm font-semibold">{title}</h3>
          {isCreate && draft && (
            <span className="pill bg-ink/5 text-ink/50">{SOURCE_LABELS[draft.source] ?? draft.source}</span>
          )}
        </div>
        {statusBadge}
      </header>

      <div className="space-y-3 px-4 py-3.5">
        {action.action === 'delete' ? (
          <p className="text-sm text-ink/70">
            确认删除账单 <span className="num font-semibold text-ink">#{action.transaction_id}</span>（不可恢复）
          </p>
        ) : (
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="金额（元）" flagged={needsReview.includes('amount')}>
              <input
                className="input num"
                type="number"
                min="0"
                step="0.01"
                inputMode="decimal"
                value={form.amount}
                disabled={locked || (!isCreate && !('amount' in patch))}
                onChange={(e) => update('amount', e.target.value)}
                placeholder="25.00"
              />
            </Field>
            <Field label="类别" flagged={needsReview.includes('category')}>
              <select
                className="input"
                value={form.category}
                disabled={locked || (!isCreate && !('category' in patch))}
                onChange={(e) => update('category', e.target.value)}
              >
                <option value="">未分类</option>
                {CATEGORIES.map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="商户 / 场景" flagged={needsReview.includes('merchant')}>
              <input
                className="input"
                value={form.merchant}
                disabled={locked || (!isCreate && !('merchant' in patch))}
                onChange={(e) => update('merchant', e.target.value)}
                placeholder="午饭"
              />
            </Field>
            <Field label="日期" flagged={needsReview.includes('occurred_at')}>
              <input
                className="input num"
                type="date"
                value={form.occurred_at}
                disabled={locked || (!isCreate && !('occurred_at' in patch))}
                onChange={(e) => update('occurred_at', e.target.value)}
              />
            </Field>
            <div className="sm:col-span-2">
              <Field label="备注" flagged={needsReview.includes('note')}>
                <input
                  className="input"
                  value={form.note}
                  disabled={locked || (!isCreate && !('note' in patch))}
                  onChange={(e) => update('note', e.target.value)}
                  placeholder="例如：和同事 AA"
                />
              </Field>
            </div>
          </div>
        )}

        {lowConfidence && !locked && action.action !== 'delete' && (
          <p className="rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-700">
            识别置信度 {Math.round((draft?.confidence ?? 0) * 100)}%
            {needsReview.length > 0 && ` · 请核对：${needsReview.map((f) => FIELD_LABELS[f] ?? f).join('、')}`}
          </p>
        )}

        {action.action === 'update' && (
          <p className="text-[11px] text-ink/40">只提交实际修改的字段，空值不会覆盖原账单。</p>
        )}

        <div className="flex items-center justify-between gap-3 pt-1">
          <p className="num text-sm text-ink/45">
            {action.action === 'delete' ? '' : `合计 ${formatMoney(valid && form.amount !== '' ? amountValue : null)}`}
          </p>
          <button
            type="button"
            className="btn-primary"
            disabled={!valid || locked}
            onClick={() => onConfirm(buildAction())}
          >
            {status === 'submitting' ? '入账中…' : status === 'failed' ? '重试确认' : '确认入账'}
          </button>
        </div>
      </div>
    </article>
  )
}

function Field({
  label,
  flagged,
  children,
}: {
  label: string
  flagged?: boolean
  children: React.ReactNode
}) {
  return (
    <label className="block">
      <span className={`label mb-1 flex items-center gap-1 ${flagged ? 'text-clay-600' : ''}`}>
        {label}
        {flagged && <span className="pill bg-clay-100 px-1.5 py-0.5 text-[10px] text-clay-600">待补</span>}
      </span>
      {children}
    </label>
  )
}
