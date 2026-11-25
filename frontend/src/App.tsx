/** 应用入口：hash 路由（#/chat 等，刷新保持当前页）+ 健康检查轮询。 */
import { useCallback, useEffect, useMemo, useState } from 'react'
import { fetchHealth } from './api/chat'
import type { HealthResponse } from './types/contract'
import { AppShell, TABS, type TabKey } from './components/AppShell'
import { useSessionId } from './hooks/useSession'
import { ChatPage } from './pages/ChatPage'
import { TransactionsPage } from './pages/TransactionsPage'
import { StatsPage } from './pages/StatsPage'
import { BudgetsPage } from './pages/BudgetsPage'

function parseHash(): TabKey {
  const key = window.location.hash.replace(/^#\/?/, '') as TabKey
  return TABS.some((tab) => tab.key === key) ? key : 'chat'
}

export default function App() {
  const [tab, setTab] = useState<TabKey>(() => parseHash())
  const [visited, setVisited] = useState<Set<TabKey>>(() => new Set<TabKey>([parseHash()]))
  const [health, setHealth] = useState<HealthResponse | null>(null)
  const [healthError, setHealthError] = useState(false)
  const session = useSessionId()

  useEffect(() => {
    function onHashChange() {
      const next = parseHash()
      setTab(next)
      setVisited((prev) => new Set(prev).add(next))
    }
    window.addEventListener('hashchange', onHashChange)
    return () => window.removeEventListener('hashchange', onHashChange)
  }, [])

  const navigate = useCallback((next: TabKey) => {
    window.location.hash = `#/${next}`
    setTab(next)
    setVisited((prev) => new Set(prev).add(next))
  }, [])

  useEffect(() => {
    let alive = true
    async function check() {
      try {
        const result = await fetchHealth()
        if (!alive) return
        setHealth(result)
        setHealthError(false)
      } catch {
        if (!alive) return
        setHealthError(true)
      }
    }
    void check()
    const timer = window.setInterval(check, 30_000)
    return () => {
      alive = false
      window.clearInterval(timer)
    }
  }, [])

  const pages = useMemo(
    () => ({
      chat: <ChatPage session={session} />,
      transactions: visited.has('transactions') ? <TransactionsPage /> : null,
      stats: visited.has('stats') ? <StatsPage /> : null,
      budgets: visited.has('budgets') ? <BudgetsPage /> : null,
    }),
    [session, visited],
  )

  return (
    <AppShell
      active={tab}
      onNavigate={navigate}
      health={health}
      healthError={healthError}
      sessionId={session.sessionId}
    >
      {/* 各页面首次访问后保持挂载：切回对话页时聊天记录与卡片状态不丢 */}
      <div className={tab === 'chat' ? 'flex min-h-0 flex-1 flex-col' : 'hidden'}>{pages.chat}</div>
      <div className={tab === 'transactions' ? '' : 'hidden'}>{pages.transactions}</div>
      <div className={tab === 'stats' ? '' : 'hidden'}>{pages.stats}</div>
      <div className={tab === 'budgets' ? '' : 'hidden'}>{pages.budgets}</div>
    </AppShell>
  )
}
