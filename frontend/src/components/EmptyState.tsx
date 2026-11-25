import type { ReactNode } from 'react'

interface EmptyStateProps {
  title: string
  description?: string
  action?: ReactNode
  icon?: string
}

export function EmptyState({ title, description, action, icon = '○' }: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 rounded-2xl border border-dashed border-line bg-paper/60 px-6 py-12 text-center">
      <span aria-hidden className="text-2xl text-ink/20">
        {icon}
      </span>
      <p className="text-sm font-medium text-ink/70">{title}</p>
      {description && <p className="max-w-sm text-xs leading-relaxed text-ink/45">{description}</p>}
      {action && <div className="mt-2">{action}</div>}
    </div>
  )
}

export function Loading({ text = '加载中…' }: { text?: string }) {
  return (
    <div className="flex items-center gap-2 px-1 py-6 text-sm text-ink/45">
      <span className="h-3 w-3 animate-spin rounded-full border-2 border-ink/20 border-t-jade-500" />
      {text}
    </div>
  )
}
