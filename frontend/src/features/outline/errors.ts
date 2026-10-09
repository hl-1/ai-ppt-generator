import { ApiError } from '@/api/client'
import type { OutlineErrorCode } from '@/features/outline/types'
import { errorMessage } from '@/lib/errors'

const OUTLINE_ERROR_MESSAGES: Record<OutlineErrorCode, string> = {
  queue_unavailable: '生成服务暂时不可用，请稍后重试。',
  input_load_failed: '读取输入材料失败，请检查后重试。',
  input_missing: '请先补充输入材料，再生成大纲。',
  travel_research_failed: '旅行资料查询未完成，请检查旅行条件和资料服务状态。',
  travel_timeout: '旅行资料查询超时，已获取的资料仍然保留，请稍后重新查询。',
  llm_not_configured: 'AI 服务尚未配置，请联系管理员。',
  model_timeout: 'AI 响应超时，请稍后重试。',
  model_unavailable: 'AI 服务暂时不可用，请稍后重试。',
  model_auth_failed: 'AI 服务凭证被拒绝，请联系管理员检查配置。',
  model_rate_limited: 'AI 服务请求受限或额度不足，请稍后重试。',
  model_request_rejected: 'AI 服务不接受当前请求，请联系管理员检查模型与参数。',
  invalid_model_output: 'AI 返回结果无法识别，请重新生成。',
  invalid_outline: '生成的大纲结构不完整，请重新生成。',
  save_failed: '大纲保存失败，请稍后重试。',
  unknown: '大纲生成失败，请稍后重试。',
}

export function outlineErrorMessage(
  code: string | null | undefined,
  fallback = OUTLINE_ERROR_MESSAGES.unknown,
): string {
  if (!code) return fallback
  return OUTLINE_ERROR_MESSAGES[code as OutlineErrorCode] ?? fallback
}

export function outlineRequestErrorMessage(error: Error | null | undefined): string {
  const fallback = error instanceof ApiError && error.status === 503
    ? OUTLINE_ERROR_MESSAGES.queue_unavailable
    : '请求未完成，请检查网络后重试。'
  return errorMessage(error, fallback)
}
