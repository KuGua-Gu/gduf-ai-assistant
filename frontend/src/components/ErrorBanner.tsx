/** 统一错误提示：展示后端 message、错误码与 trace_id（便于按契约排查）。 */
import type { ApiError } from '../api/client'

interface ErrorBannerProps {
  error: ApiError
  onRetry?: () => void
  onDismiss?: () => void
  compact?: boolean
}

export function ErrorBanner({ error, onRetry, onDismiss, compact = false }: ErrorBannerProps) {
  return (
    <div
      role="alert"
      className={`flex flex-wrap items-start gap-x-3 gap-y-2 rounded-xl border border-clay-500/25 bg-clay-100/70 text-clay-600 ${
        compact ? 'px-3 py-2 text-xs' : 'px-4 py-3 text-sm'
      }`}
    >
      <div className="min-w-0 flex-1">
        <p className="font-medium">{error.message}</p>
        <p className="mt-1 flex flex-wrap items-center gap-x-3 text-[11px] text-clay-600/70">
          <span className="num">{error.code}</span>
          {error.traceId && <span>trace {error.traceId}</span>}
        </p>
      </div>
      <div className="flex items-center gap-2">
        {onRetry && error.retryable && (
          <button type="button" className="btn-ghost !px-2.5 !py-1 !text-xs" onClick={onRetry}>
            重试
          </button>
        )}
        {onDismiss && (
          <button
            type="button"
            className="rounded-lg px-2 py-1 text-xs text-clay-600/70 hover:text-clay-600"
            onClick={onDismiss}
          >
            关闭
          </button>
        )}
      </div>
    </div>
  )
}
