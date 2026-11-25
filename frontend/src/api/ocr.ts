/**
 * 小票上传（成员 4 提供的 POST /api/ocr/upload）。
 * 本仓库当前未提供该接口，因此这里把 404/501 归一成 OCR_UNAVAILABLE，
 * 页面据此提示「图片识别未接入」并允许手动填写 image_id。
 */
import { ApiError } from './client'
import { http } from './client'
import type { OcrUploadResponse } from '../types/contract'

export async function uploadReceipt(file: File): Promise<string> {
  const form = new FormData()
  form.append('file', file)
  try {
    const { data } = await http.post<OcrUploadResponse | { imageId?: string }>('/ocr/upload', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 30_000,
    })
    const imageId = (data as OcrUploadResponse).image_id ?? (data as { imageId?: string }).imageId
    if (!imageId) {
      throw new ApiError({
        code: 'OCR_UNAVAILABLE',
        message: '上传接口没有返回 image_id，图片识别可能尚未接入。',
        status: 200,
      })
    }
    return imageId
  } catch (error) {
    if (error instanceof ApiError && (error.status === 404 || error.status === 405 || error.status === 501)) {
      throw new ApiError({
        code: 'OCR_UNAVAILABLE',
        message: '图片识别接口尚未接入（成员 4 负责），可以先手动告诉我金额和类别。',
        status: error.status,
        traceId: error.traceId,
      })
    }
    throw error
  }
}
