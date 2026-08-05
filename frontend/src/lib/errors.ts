import { ApiError, type ApiErrorDetail } from '@/api/client'

function detailToMessage(detail: ApiErrorDetail): string | null {
  if (typeof detail === 'string') return detail

  if (Array.isArray(detail) && detail.length > 0) {
    const first = detail[0]
    if (first && typeof first === 'object' && 'msg' in first) {
      const msg = (first as { msg: unknown }).msg
      if (typeof msg === 'string') return msg
    }
  }

  if (detail && typeof detail === 'object' && 'message' in detail) {
    const message = (detail as { message: unknown }).message
    if (typeof message === 'string') return message
  }

  return null
}

/** 接口错误直接展示后端给的中文说明，其余一律收敛为通用提示 */
export function errorMessage(error: Error | null | undefined, fallback = '操作失败，请稍后重试。') {
  if (!error) return fallback
  if (!(error instanceof ApiError)) return fallback
  return detailToMessage(error.detail) ?? fallback
}
