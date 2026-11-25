/** 对话相关接口：POST /api/chat、/api/chat/confirm、DELETE /api/chat/session/{id}、GET /api/health */
import { apiDelete, apiGet, apiPost } from './client'
import type {
  ChatRequest,
  ChatResponse,
  ConfirmRequest,
  ConfirmResponse,
  HealthResponse,
} from '../types/contract'

export function sendMessage(payload: ChatRequest): Promise<ChatResponse> {
  return apiPost<ChatResponse>('/chat', payload)
}

/**
 * 确认入账。`actions` 必须原样使用上一条响应里的 `pending_actions`
 * （前端可在卡片里改动 draft 的可编辑字段，其余字段保持原值）。
 */
export function confirmActions(payload: ConfirmRequest): Promise<ConfirmResponse> {
  return apiPost<ConfirmResponse>('/chat/confirm', payload)
}

/** 「新会话」：清空后端会话记忆与待补齐草稿。 */
export function clearSession(sessionId: string): Promise<{ cleared: boolean }> {
  return apiDelete<{ cleared: boolean }>(`/chat/session/${encodeURIComponent(sessionId)}`)
}

export function fetchHealth(): Promise<HealthResponse> {
  return apiGet<HealthResponse>('/health')
}
