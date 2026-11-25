/** 应用外壳：品牌区、主导航、后端/会话状态。桌面为侧栏，移动为底部标签。 */
import type { ReactNode } from 'react'
import type { HealthResponse } from '../types/contract'

export type TabKey = 'chat' | 'transactions' | 'stats' | 'budgets'

export const TABS: { key: TabKey; label: string; hint: string; icon: ReactNode }[] = [
  { key: 'chat', label: '对话记账', hint: '说一句话就记一笔', icon: <ChatIcon /> },
  { key: 'transactions', label: '账单流水', hint: '筛选、修改、删除', icon: <ListIcon /> },
  { key: 'stats', label: '消费统计', hint: '类别占比与趋势', icon: <ChartIcon /> },
  { key: 'budgets', label: '月度预算', hint: '设置与超支提醒', icon: <GaugeIcon /> },
]

interface AppShellProps {
  active: TabKey
  onNavigate: (tab: TabKey) => void
  health: HealthResponse | null
  healthError: boolean
  sessionId: string
  children: ReactNode
}

export function AppShell({ active, onNavigate, health, healthError, sessionId, children }: AppShellProps) {
  return (
    <div className="mx-auto flex min-h-full w-full max-w-7xl flex-col gap-0 lg:flex-row lg:gap-6 lg:px-6 lg:py-6">
      {/* 侧栏（桌面） */}
      <aside className="hidden w-64 shrink-0 flex-col justify-between lg:flex">
        <div>
          <Brand />
          <nav className="mt-8 space-y-1">
            {TABS.map((tab) => (
              <button
                key={tab.key}
                type="button"
                onClick={() => onNavigate(tab.key)}
                aria-current={active === tab.key ? 'page' : undefined}
                className={`group flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left transition ${
                  active === tab.key
                    ? 'bg-jade-600 text-white shadow-card'
                    : 'text-ink/70 hover:bg-paper hover:text-ink'
                }`}
              >
                <span className={active === tab.key ? 'text-white' : 'text-jade-600'}>{tab.icon}</span>
                <span className="flex-1">
                  <span className="block text-sm font-medium">{tab.label}</span>
                  <span
                    className={`block text-[11px] ${
                      active === tab.key ? 'text-white/70' : 'text-ink/40'
                    }`}
                  >
                    {tab.hint}
                  </span>
                </span>
              </button>
            ))}
          </nav>
        </div>
        <div className="space-y-3 pb-2">
          <HealthPill health={health} healthError={healthError} />
          <SessionPill sessionId={sessionId} />
          <p className="text-[11px] leading-relaxed text-ink/35">
            数据存于本地 SQLite；对话与统计接口见 docs/api-contract.md。
          </p>
        </div>
      </aside>

      {/* 移动端顶栏 */}
      <header className="flex items-center justify-between gap-3 px-4 pb-3 pt-4 lg:hidden">
        <Brand compact />
        <HealthPill health={health} healthError={healthError} compact />
      </header>

      <main className="flex min-w-0 flex-1 flex-col px-3 pb-24 lg:px-0 lg:pb-0">{children}</main>

      {/* 移动端底部导航 */}
      <nav className="fixed inset-x-0 bottom-0 z-20 flex border-t border-line bg-paper/95 backdrop-blur lg:hidden">
        {TABS.map((tab) => (
          <button
            key={tab.key}
            type="button"
            onClick={() => onNavigate(tab.key)}
            aria-current={active === tab.key ? 'page' : undefined}
            className={`flex flex-1 flex-col items-center gap-0.5 py-2.5 text-[11px] transition ${
              active === tab.key ? 'text-jade-700' : 'text-ink/45'
            }`}
          >
            <span className={active === tab.key ? 'text-jade-600' : 'text-ink/35'}>{tab.icon}</span>
            {tab.label}
          </button>
        ))}
      </nav>
    </div>
  )
}

function Brand({ compact = false }: { compact?: boolean }) {
  return (
    <div className="flex items-center gap-3">
      <div className="flex h-10 w-10 items-center justify-center rounded-2xl bg-jade-600 text-lg font-semibold text-white shadow-card">
        账
      </div>
      <div className={compact ? 'hidden sm:block' : ''}>
        <p className="text-sm font-semibold leading-tight">记账助手</p>
        <p className="text-[11px] text-ink/45">自然语言记账 · 消费分析</p>
      </div>
    </div>
  )
}

function HealthPill({
  health,
  healthError,
  compact = false,
}: {
  health: HealthResponse | null
  healthError: boolean
  compact?: boolean
}) {
  if (healthError) {
    return (
      <span className="pill bg-clay-100 text-clay-600">
        <span className="h-1.5 w-1.5 rounded-full bg-clay-500" />
        {compact ? '后端未连接' : '后端未连接，请启动 uvicorn'}
      </span>
    )
  }
  if (!health) {
    return (
      <span className="pill bg-ink/5 text-ink/45">
        <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-ink/30" />
        连接中…
      </span>
    )
  }
  return (
    <span
      className={`pill ${
        health.llm_configured ? 'bg-jade-50 text-jade-700' : 'bg-amber-50 text-amber-700'
      }`}
      title={health.llm_configured ? `模型：${health.llm_model}` : '未配置 LLM_API_KEY，运行在离线规则模式'}
    >
      <span
        className={`h-1.5 w-1.5 rounded-full ${health.llm_configured ? 'bg-jade-500' : 'bg-amber-500'}`}
      />
      {health.llm_configured ? `模型已就绪 · ${health.llm_model}` : compact ? '离线规则模式' : '离线规则模式（未配置 Key）'}
    </span>
  )
}

function SessionPill({ sessionId }: { sessionId: string }) {
  return (
    <div className="rounded-xl border border-line bg-paper/70 px-3 py-2">
      <p className="label">当前会话</p>
      <p className="num mt-0.5 truncate text-xs text-ink/60" title={sessionId || '尚未创建'}>
        {sessionId ? sessionId : '首条消息后自动创建'}
      </p>
    </div>
  )
}

/* ---------- 图标（内联 SVG，避免额外依赖） ---------- */

function ChatIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7">
      <path d="M21 12a8 8 0 1 1-3.2-6.4" strokeLinecap="round" />
      <path d="M21 4v5h-5" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M8 11h8M8 15h5" strokeLinecap="round" />
    </svg>
  )
}

function ListIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7">
      <path d="M4 6h16M4 12h16M4 18h10" strokeLinecap="round" />
    </svg>
  )
}

function ChartIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7">
      <path d="M5 19V9M12 19V5M19 19v-7" strokeLinecap="round" />
    </svg>
  )
}

function GaugeIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7">
      <circle cx="12" cy="12" r="8" />
      <path d="M12 12l3.5-3.5" strokeLinecap="round" />
    </svg>
  )
}
