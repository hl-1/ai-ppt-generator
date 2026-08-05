import { ApiError } from '@/api/client'

/** 接口错误直接展示后端给的中文说明，其余一律收敛为通用提示 */
export function errorMessage(error: Error | null | undefined, fallback = '操作失败，请稍后重试。') {
  if (!error) return fallback
  return error instanceof ApiError ? error.detail : fallback
}
