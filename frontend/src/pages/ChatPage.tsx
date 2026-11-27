/**
 * 对话页：发送消息 → 渲染回复 + 确认卡片 → 确认入账。
 * 会话 ID 存 localStorage；「新会话」调用 DELETE /api/chat/session/{id}。
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import type { ApiError } from '../api/client'
import { clearSession, confirmActions, sendMessage } from '../api/chat'
import { toApiError } from '../api/client'
import { uploadReceipt } from '../api/ocr'
import type { Intent, PendingAction } from '../types/contract'
import { ConfirmCard, type CardStatus } from '../components/ConfirmCard'
import { ErrorBanner } from '../components/ErrorBanner'
import type { SessionState } from '../hooks/useSession'

type Bubble =
  | { kind: 'user'; id: string; text: string; imageId?: string }
  | {
      kind: 'assistant'
      id: string
      text: string
      intent?: Intent
      traceId?: string
      actions: PendingAction[]
      cardStatus: Record<number, CardStatus>
      /** 契约字段：true 时才允许渲染确认按钮 */
      confirmRequired: boolean
      note?: string
    }

const INTENT_LABELS: Record<Intent, { text: string; cls: string }> = {
  record_expense: { text: '记账', cls: 'bg-jade-50 text-jade-700' },
  query_stats: { text: '查账', cls: 'bg-blue-50 text-blue-700' },
  manage_budget: { text: '预算', cls: 'bg-amber-50 text-amber-700' },
  confirm_action: { text: '待确认', cls: 'bg-clay-100 text-clay-600' },
  chitchat: { text: '闲聊', cls: 'bg-ink/5 text-ink/55' },
  refuse: { text: '已拒绝', cls: 'bg-clay-100 text-clay-600' },
}

const EXAMPLES = [
  '午饭 25 元',
  '打车上班 18 块，晚饭 32',
  '这个月餐饮花了多少',
  '这个月哪类花得最多',
  '这个月餐饮预算 1500',
  '这个月预算还剩多少',
]

let seq = 0
function nextId(prefix: string) {
  seq += 1
  return `${prefix}-${Date.now()}-${seq}`
}

/** 给一组卡片设置同一个状态，避免 Object.fromEntries 推导出 string 索引签名。 */
function statusMap(actions: PendingAction[], status: CardStatus): Record<number, CardStatus> {
  const out: Record<number, CardStatus> = {}
  actions.forEach((_, index) => {
    out[index] = status
  })
  return out
}

export function ChatPage({ session }: { session: SessionState }) {
  const { sessionId, setSessionId, reset } = session
  const [messages, setMessages] = useState<Bubble[]>([])
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<ApiError | null>(null)
  const [lastAttempt, setLastAttempt] = useState<{ text: string; imageId?: string } | null>(null)
  const [imageId, setImageId] = useState('')
  const [imageName, setImageName] = useState('')
  const [uploading, setUploading] = useState(false)
  const [manualImageOpen, setManualImageOpen] = useState(false)
  const [hint, setHint] = useState('')
  const bottomRef = useRef<HTMLDivElement | null>(null)
  const fileRef = useRef<HTMLInputElement | null>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [messages, busy])

  const submit = useCallback(
    async (text: string, attachedImageId?: string) => {
      const trimmed = text.trim()
      if (!trimmed || busy) return
      const attempt = { text: trimmed, imageId: attachedImageId || undefined }
      setLastAttempt(attempt)
      setError(null)
      setHint('')
      setBusy(true)
      setMessages((prev) => [
        ...prev,
        { kind: 'user', id: nextId('u'), text: trimmed, imageId: attempt.imageId },
      ])
      setInput('')
      try {
        const res = await sendMessage({
          session_id: sessionId || undefined,
          message: trimmed,
          image_id: attempt.imageId ?? undefined,
        })
        setSessionId(res.session_id)
        setImageId('')
        setImageName('')
        const statuses: Record<number, CardStatus> = {}
        res.pending_actions.forEach((_, i) => {
          statuses[i] = 'pending'
        })
        setMessages((prev) => [
          ...prev,
          {
            kind: 'assistant',
            id: nextId('a'),
            text: res.reply,
            intent: res.intent,
            traceId: res.trace_id,
            actions: res.pending_actions,
            cardStatus: statuses,
            confirmRequired: res.confirm_required,
          },
        ])
      } catch (err) {
        const apiError = toApiError(err)
        setError(apiError)
        setMessages((prev) => [
          ...prev,
          {
            kind: 'assistant',
            id: nextId('a'),
            text: apiError.message,
            actions: [],
            cardStatus: {},
            confirmRequired: false,
            note: `${apiError.code}${apiError.traceId ? ` · trace ${apiError.traceId}` : ''}`,
          },
        ])
      } finally {
        setBusy(false)
      }
    },
    [busy, sessionId, setSessionId],
  )

  const handleConfirm = useCallback(
    async (messageId: string, index: number, action: PendingAction, allOf?: PendingAction[]) => {
      if (!sessionId) {
        setError(
          toApiError(new Error('会话尚未创建，请先发送一条消息')),
        )
        return
      }
      const targets = allOf ?? [action]
      setMessages((prev) =>
        prev.map((m) =>
          m.kind === 'assistant' && m.id === messageId
            ? {
                ...m,
                cardStatus: allOf
                  ? statusMap(m.actions, 'submitting')
                  : { ...m.cardStatus, [index]: 'submitting' as CardStatus },
              }
            : m,
        ),
      )
      try {
        const res = await confirmActions({ session_id: sessionId, actions: targets })
        const ok = res.created > 0
        setMessages((prev) => {
          const next = prev.map((m) =>
            m.kind === 'assistant' && m.id === messageId
              ? {
                  ...m,
                  cardStatus: allOf
                    ? statusMap(m.actions, ok ? 'confirmed' : 'failed')
                    : { ...m.cardStatus, [index]: (ok ? 'confirmed' : 'failed') as CardStatus },
                }
              : m,
          )
          return [
            ...next,
            {
              kind: 'assistant' as const,
              id: nextId('a'),
              text: res.reply,
              actions: [],
              cardStatus: {},
              confirmRequired: false,
              note: `created ${res.created} · failed ${res.failed} · trace ${res.trace_id}`,
            },
          ]
        })
        setError(null)
      } catch (err) {
        const apiError = toApiError(err)
        setError(apiError)
        // 确认失败由卡片自带的「重试确认」处理，避免误重发上一条消息
        setLastAttempt(null)
        setMessages((prev) =>
          prev.map((m) =>
            m.kind === 'assistant' && m.id === messageId
              ? {
                  ...m,
                  cardStatus: allOf
                    ? statusMap(m.actions, 'failed')
                    : { ...m.cardStatus, [index]: 'failed' as CardStatus },
                }
              : m,
          ),
        )
      }
    },
    [sessionId],
  )

  async function handleNewSession() {
    if (sessionId) {
      try {
        await clearSession(sessionId)
      } catch {
        /* 清空失败也继续本地重置，避免卡住演示 */
      }
    }
    reset()
    setMessages([])
    setError(null)
    setHint('')
    setImageId('')
    setImageName('')
    setInput('')
  }

  async function handleFile(file: File | undefined) {
    if (!file) return
    setHint('')
    setUploading(true)
    try {
      const uploaded = await uploadReceipt(file)
      setImageId(uploaded.imageId)
      setImageName(uploaded.filename || file.name)
      setHint('小票已上传，发送消息后助手会识别并生成确认卡片。')
    } catch (err) {
      const apiError = toApiError(err)
      setHint(apiError.message)
      // 只有接口不可用/网络异常时才提示手动输入兜底
      if (apiError.code === 'OCR_UNAVAILABLE' || apiError.code === 'NETWORK_ERROR') {
        setManualImageOpen(true)
      }
    } finally {
      setUploading(false)
      if (fileRef.current) fileRef.current.value = ''
    }
  }

  function clearUpload() {
    setImageId('')
    setImageName('')
    setHint('')
  }

  return (
    <div className="flex h-full min-h-0 flex-col lg:h-[calc(100vh-3rem)]">
      <div className="flex items-center justify-between gap-3 px-1 pb-3 pt-1 lg:px-0">
        <div>
          <h1 className="text-lg font-semibold">对话记账</h1>
          <p className="text-xs text-ink/45">一句话记账；写操作先出确认卡片，确认后才入账。</p>
        </div>
        <button type="button" className="btn-ghost !py-1.5 !text-xs" onClick={handleNewSession}>
          新会话
        </button>
      </div>

      <div className="card flex min-h-0 flex-1 flex-col overflow-hidden">
        <div className="scroll-thin min-h-0 flex-1 space-y-4 overflow-y-auto px-4 py-5 lg:px-6">
          {messages.length === 0 && (
            <Welcome
              onPick={(text) => {
                setInput(text)
                void submit(text)
              }}
            />
          )}

          {messages.map((message) =>
            message.kind === 'user' ? (
              <div key={message.id} className="flex justify-end">
                <div className="max-w-[82%] rounded-2xl rounded-br-md bg-jade-600 px-4 py-2.5 text-sm text-white shadow-card">
                  {message.text}
                  {message.imageId && (
                    <p className="mt-1 text-[11px] text-white/70">附件 image_id：{message.imageId}</p>
                  )}
                </div>
              </div>
            ) : (
              <div key={message.id} className="animate-rise space-y-3">
                <div className="flex items-start gap-2.5">
                  <span className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-jade-50 text-xs font-semibold text-jade-700">
                    AI
                  </span>
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      {message.intent && (
                        <span className={`pill ${INTENT_LABELS[message.intent].cls}`}>
                          {INTENT_LABELS[message.intent].text}
                        </span>
                      )}
                      {message.traceId && (
                        <span className="num text-[10px] text-ink/25">trace {message.traceId}</span>
                      )}
                    </div>
                    <p className="mt-1 whitespace-pre-wrap break-words text-sm leading-relaxed text-ink/85">
                      {message.text}
                    </p>
                    {message.note && <p className="num mt-1 text-[10px] text-ink/30">{message.note}</p>}
                  </div>
                </div>

                {message.confirmRequired && message.actions.length > 0 && (
                  <div className="space-y-3 pl-9">
                    {message.actions.map((action, index) => (
                      <ConfirmCard
                        key={`${message.id}-${index}`}
                        action={action}
                        index={index}
                        status={message.cardStatus[index] ?? 'pending'}
                        onConfirm={(next) => void handleConfirm(message.id, index, next)}
                      />
                    ))}
                    {message.actions.length > 1 && (
                      <button
                        type="button"
                        className="btn-ghost !py-1.5 !text-xs"
                        disabled={Object.values(message.cardStatus).some((s) => s !== 'pending')}
                        onClick={() =>
                          void handleConfirm(
                            message.id,
                            0,
                            message.actions[0],
                            Object.values(message.cardStatus).some((s) => s === 'pending')
                              ? message.actions
                              : undefined,
                          )
                        }
                      >
                        全部确认（{message.actions.length} 笔）
                      </button>
                    )}
                  </div>
                )}
              </div>
            ),
          )}

          {busy && (
            <div className="flex items-center gap-2 pl-9 text-xs text-ink/40">
              <span className="h-3 w-3 animate-spin rounded-full border-2 border-ink/15 border-t-jade-500" />
              助手正在解析…
            </div>
          )}
          <div ref={bottomRef} />
        </div>

        <div className="border-t border-line/70 bg-paper px-3 py-3 lg:px-4">
          {error && (
            <div className="mb-2">
              <ErrorBanner
                error={error}
                compact
                onRetry={
                  lastAttempt
                    ? () => {
                        void submit(lastAttempt.text, lastAttempt.imageId)
                      }
                    : undefined
                }
                onDismiss={() => setError(null)}
              />
            </div>
          )}
          {hint && <p className="mb-2 text-[11px] text-amber-700">{hint}</p>}

          {(imageId || manualImageOpen) && (
            <div className="mb-2 flex flex-wrap items-center gap-2 text-[11px] text-ink/55">
              {imageId ? (
                <span className="pill bg-jade-50 text-jade-700">
                  附件：{imageName || '小票'} · {imageId.slice(0, 8)}…
                  <button
                    type="button"
                    className="ml-1 text-jade-700/60 hover:text-jade-700"
                    onClick={clearUpload}
                    aria-label="移除附件"
                  >
                    ×
                  </button>
                </span>
              ) : (
                <>
                  <input
                    className="input !w-56 !py-1 !text-xs"
                    placeholder="手动填写 image_id"
                    value={imageId}
                    onChange={(e) => setImageId(e.target.value)}
                  />
                  <span className="text-ink/35">上传接口异常时的兜底：粘贴已上传的 image_id</span>
                </>
              )}
            </div>
          )}

          <form
            className="flex items-end gap-2"
            onSubmit={(event) => {
              event.preventDefault()
              void submit(input, imageId || undefined)
            }}
          >
            <button
              type="button"
              className="btn-ghost !px-2.5"
              title="上传小票 / 支付截图（JPG/PNG/WEBP，≤10MB）"
              disabled={uploading}
              onClick={() => fileRef.current?.click()}
            >
              {uploading ? (
                <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-ink/20 border-t-jade-500" />
              ) : (
                <PaperclipIcon />
              )}
            </button>
            <input
              ref={fileRef}
              type="file"
              accept="image/png,image/jpeg,image/webp"
              className="hidden"
              onChange={(e) => void handleFile(e.target.files?.[0])}
            />
            <textarea
              className="input max-h-32 min-h-[42px] flex-1 resize-none py-2.5"
              rows={1}
              maxLength={2000}
              placeholder="例如：午饭 25 元 / 这个月餐饮花了多少 / 这个月餐饮预算 1500"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault()
                  void submit(input, imageId || undefined)
                }
              }}
            />
            <button type="submit" className="btn-primary" disabled={busy || !input.trim()}>
              发送
            </button>
          </form>
          <p className="mt-1.5 text-[10px] text-ink/30">
            Enter 发送 · Shift+Enter 换行 · 越界请求（套现、伪造流水等）会被直接拒绝
          </p>
        </div>
      </div>
    </div>
  )
}

function Welcome({ onPick }: { onPick: (text: string) => void }) {
  return (
    <div className="mx-auto max-w-xl space-y-5 py-6 text-center">
      <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-2xl bg-jade-600 text-xl font-semibold text-white shadow-card">
        账
      </div>
      <div>
        <h2 className="text-base font-semibold">说一句话，就记一笔</h2>
        <p className="mt-1 text-xs leading-relaxed text-ink/50">
          自动解析金额、类别与日期并生成确认卡片；也可以查账、看统计、设预算，或上传小票识别。
        </p>
      </div>
      <div className="flex flex-wrap justify-center gap-2">
        {EXAMPLES.map((example) => (
          <button
            key={example}
            type="button"
            onClick={() => onPick(example)}
            className="rounded-full border border-line bg-paper px-3 py-1.5 text-xs text-ink/70 transition hover:border-jade-300 hover:text-jade-700"
          >
            {example}
          </button>
        ))}
      </div>
    </div>
  )
}

function PaperclipIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7">
      <path
        d="M20 11.5 12.3 19.2a4.5 4.5 0 0 1-6.4-6.4l7.1-7.1a3 3 0 0 1 4.2 4.2l-7 7a1.5 1.5 0 0 1-2.2-2.1l6.3-6.3"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}
