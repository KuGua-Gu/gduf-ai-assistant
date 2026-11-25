/** 轻量模态框：仅用于账单编辑/删除确认，不引入额外依赖。 */
import { useEffect, type ReactNode } from 'react'

interface ModalProps {
  open: boolean
  title: string
  description?: string
  onClose: () => void
  children?: ReactNode
  footer?: ReactNode
}

export function Modal({ open, title, description, onClose, children, footer }: ModalProps) {
  useEffect(() => {
    if (!open) return
    function onKey(event: KeyboardEvent) {
      if (event.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [open, onClose])

  if (!open) return null

  return (
    <div className="fixed inset-0 z-40 flex items-end justify-center bg-ink/30 p-0 backdrop-blur-sm sm:items-center sm:p-4">
      <div
        role="dialog"
        aria-modal="true"
        aria-label={title}
        className="w-full max-w-md animate-rise rounded-t-2xl border border-line bg-paper p-5 shadow-card sm:rounded-2xl"
      >
        <div className="flex items-start justify-between gap-4">
          <div>
            <h2 className="text-base font-semibold">{title}</h2>
            {description && <p className="mt-1 text-xs text-ink/50">{description}</p>}
          </div>
          <button
            type="button"
            className="rounded-lg px-2 py-1 text-ink/40 hover:text-ink"
            onClick={onClose}
            aria-label="关闭"
          >
            ×
          </button>
        </div>
        {children && <div className="mt-4 space-y-3">{children}</div>}
        {footer && <div className="mt-5 flex justify-end gap-2">{footer}</div>}
      </div>
    </div>
  )
}
