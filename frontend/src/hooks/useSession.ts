/**
 * 会话 ID 管理：存 localStorage，刷新页面后继续同一段对话。
 * 后端在首次请求时创建 session_id 并在响应里返回，前端以响应值为准。
 */
import { useCallback, useEffect, useState } from 'react'

const STORAGE_KEY = 'gduf.session_id'

function readStored(): string {
  try {
    return localStorage.getItem(STORAGE_KEY) ?? ''
  } catch {
    return ''
  }
}

export function useSessionId() {
  const [sessionId, setSessionId] = useState<string>(() => readStored())

  useEffect(() => {
    try {
      if (sessionId) localStorage.setItem(STORAGE_KEY, sessionId)
      else localStorage.removeItem(STORAGE_KEY)
    } catch {
      /* 隐私模式下忽略存储失败，会话仍可在内存中继续 */
    }
  }, [sessionId])

  const reset = useCallback(() => {
    setSessionId('')
    try {
      localStorage.removeItem(STORAGE_KEY)
    } catch {
      /* ignore */
    }
  }, [])

  return { sessionId, setSessionId, reset }
}

export type SessionState = ReturnType<typeof useSessionId>
