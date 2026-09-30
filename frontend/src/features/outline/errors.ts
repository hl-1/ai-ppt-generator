import { ApiError } from '@/api/client'
import type { OutlineErrorCode } from '@/features/outline/types'

const OUTLINE_ERROR_MESSAGES: Record<OutlineErrorCode, string> = {
  queue_unavailable: '生成服务暂时不可用，请稍后重试。',
  input_load_failed: '读取输入材料失败，请检查后重试。',
  input_missing: '请先补充输入材料，再生成大纲。',
  llm_not_configured: 'AI 服务尚未配置，请联系管理员。',
  model_timeout: 'AI 响应超时，请稍后重试。',
  model_unavailable: 'AI 服务暂时不可用，请稍后重试。',
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
  if (!(error instanceof ApiError)) return OUTLINE_ERROR_MESSAGES.unknown
  if (error.status === 422) return OUTLINE_ERROR_MESSAGES.input_missing
  if (error.status === 503) return OUTLINE_ERROR_MESSAGES.queue_unavailable
  if (error.status === 409) return '大纲正在生成，请稍候。'
  return OUTLINE_ERROR_MESSAGES.unknown
}
