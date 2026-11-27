/**
 * 小票上传：``POST /api/ocr/upload``（成员 4，multipart 字段 ``file``）。
 * 返回 ``image_id``，随后放进 ``POST /api/chat`` 的 ``image_id`` 字段。
 *
 * 前端先做一次类型/大小预校验，避免上传必然被拒的文件；
 * 服务端的 415/413/422 错误体（{code,message,trace_id}）由拦截器统一透传。
 */
import { ApiError, http } from './client'
import type { OcrUploadResponse } from '../types/contract'

/** 与服务端 ``OCR_MAX_BYTES`` 默认值保持一致。 */
export const MAX_RECEIPT_BYTES = 10 * 1024 * 1024
const ALLOWED_MIME = ['image/jpeg', 'image/png', 'image/webp']
const ALLOWED_EXT = /\.(jpe?g|png|webp)$/i

export interface UploadedReceipt {
  imageId: string
  filename: string
  size: number
}

export async function uploadReceipt(file: File): Promise<UploadedReceipt> {
  if (!ALLOWED_MIME.includes(file.type) && !ALLOWED_EXT.test(file.name)) {
    throw new ApiError({
      code: 'INVALID_FILE_TYPE',
      message: '只支持 JPG/PNG/WEBP 格式的小票图片。',
      status: 0,
    })
  }
  if (file.size === 0) {
    throw new ApiError({ code: 'EMPTY_FILE', message: '上传的图片是空的，请重新选择。', status: 0 })
  }
  if (file.size > MAX_RECEIPT_BYTES) {
    throw new ApiError({
      code: 'FILE_TOO_LARGE',
      message: `图片不能超过 ${MAX_RECEIPT_BYTES / 1024 / 1024} MB。`,
      status: 0,
    })
  }

  const form = new FormData()
  form.append('file', file)
  const { data } = await http.post<OcrUploadResponse>('/ocr/upload', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 30_000,
  })
  if (!data?.image_id) {
    throw new ApiError({
      code: 'OCR_UNAVAILABLE',
      message: '上传接口没有返回 image_id，请重试或手动输入。',
      status: 200,
    })
  }
  return { imageId: data.image_id, filename: data.filename ?? '', size: data.size ?? file.size }
}
