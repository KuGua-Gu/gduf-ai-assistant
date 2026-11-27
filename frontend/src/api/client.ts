/**
 * axios 统一封装。
 * - baseURL 默认 `/api`（开发走 Vite 代理，生产由 FastAPI 托管 dist）；
 * - 拦截器把后端的 `{code,message,trace_id}` 与网络错误统一成 ApiError，
 *   页面只处理一种错误形状（docs/api-contract.md「错误码」章节）。
 */
import axios, { AxiosError } from 'axios'
import type { ApiErrorBody } from '../types/contract'

export const API_BASE = (import.meta.env.VITE_API_BASE as string | undefined)?.replace(/\/$/, '') ?? '/api'

/** 业务错误码（与契约保持同步）。 */
export type ApiErrorCode =
  | 'VALIDATION_ERROR'
  | 'LLM_UNAVAILABLE'
  | 'OUTPUT_FORMAT_ERROR'
  | 'TOOL_EXECUTION_ERROR'
  | 'CONTEXT_OVERFLOW'
  | 'SAFETY_VIOLATION'
  | 'AGENT_ERROR'
  | 'TRANSACTION_NOT_FOUND'
  | 'INVALID_FILE_TYPE'
  | 'FILE_TOO_LARGE'
  | 'EMPTY_FILE'
  | 'NETWORK_ERROR'
  | 'OCR_UNAVAILABLE'

export class ApiError extends Error {
  readonly code: ApiErrorCode
  readonly status: number
  readonly traceId: string
  /** 便于错误态 UI 决定是否展示「重试」按钮。 */
  readonly retryable: boolean

  constructor(params: {
    code: ApiErrorCode
    message: string
    status: number
    traceId?: string
    retryable?: boolean
  }) {
    super(params.message)
    this.name = 'ApiError'
    this.code = params.code
    this.status = params.status
    this.traceId = params.traceId ?? ''
    this.retryable = params.retryable ?? false
  }
}

const FALLBACK_MESSAGES: Record<string, string> = {
  VALIDATION_ERROR: '请求参数不合法，请检查后重试。',
  LLM_UNAVAILABLE: '模型服务暂时不可用，请稍等片刻再试；也可以先在账单页手动记一笔。',
  OUTPUT_FORMAT_ERROR: '刚才没有理解清楚，换个说法（例如「午饭 25 元」）再试一次？',
  TOOL_EXECUTION_ERROR: '数据读写没有成功，这笔记录还没有保存，请稍后重试。',
  CONTEXT_OVERFLOW: '当前对话太长了，点「新会话」后可以继续。',
  SAFETY_VIOLATION: '这类请求我无法协助。',
  AGENT_ERROR: '服务出了点小问题，请稍后再试一次。',
  TRANSACTION_NOT_FOUND: '没有找到这笔账单。',
  INVALID_FILE_TYPE: '只支持 JPG/PNG/WEBP 格式的小票图片。',
  FILE_TOO_LARGE: '图片不能超过 10 MB。',
  EMPTY_FILE: '上传的图片是空的，请重新选择。',
  OCR_UNAVAILABLE: '图片上传没有成功，请重试或手动输入 image_id。',
}

export function toApiError(error: unknown): ApiError {
  if (error instanceof ApiError) return error

  const axiosError = error as AxiosError<Partial<ApiErrorBody>>
  if (axiosError?.isAxiosError) {
    const response = axiosError.response
    if (!response) {
      return new ApiError({
        code: 'NETWORK_ERROR',
        message: '连接不上后端服务，请确认 uvicorn 已在 127.0.0.1:8000 启动。',
        status: 0,
        retryable: true,
      })
    }
    const body = response.data ?? {}
    const code = (body.code as ApiErrorCode | undefined) ?? 'AGENT_ERROR'
    const fallback = FALLBACK_MESSAGES[code] ?? '请求失败，请稍后再试。'
    return new ApiError({
      code,
      message: body.message?.trim() || fallback,
      status: response.status,
      traceId: body.trace_id,
      retryable: response.status >= 500 || code === 'NETWORK_ERROR',
    })
  }

  return new ApiError({
    code: 'AGENT_ERROR',
    message: error instanceof Error ? error.message : '未知错误，请稍后再试。',
    status: 0,
  })
}

export const http = axios.create({
  baseURL: API_BASE,
  timeout: 60_000,
  headers: { 'Content-Type': 'application/json' },
})

http.interceptors.response.use(
  (response) => response,
  (error) => Promise.reject(toApiError(error)),
)

/** 统一取出 data，调用方直接拿业务对象。 */
export async function apiGet<T>(url: string, params?: Record<string, unknown>): Promise<T> {
  const { data } = await http.get<T>(url, { params })
  return data
}

export async function apiPost<T>(url: string, body?: unknown): Promise<T> {
  const { data } = await http.post<T>(url, body)
  return data
}

export async function apiPatch<T>(url: string, body?: unknown): Promise<T> {
  const { data } = await http.patch<T>(url, body)
  return data
}

export async function apiPut<T>(url: string, body?: unknown): Promise<T> {
  const { data } = await http.put<T>(url, body)
  return data
}

export async function apiDelete<T>(url: string): Promise<T> {
  const { data } = await http.delete<T>(url)
  return data
}
