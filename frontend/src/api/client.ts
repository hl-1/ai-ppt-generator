import { tokenStore } from '@/features/auth/token'

export class ApiError extends Error {
  readonly status: number
  readonly detail: string

  constructor(status: number, detail: string) {
    super(detail)
    this.name = 'ApiError'
    this.status = status
    this.detail = detail
  }
}

const API_PREFIX = '/api/v1'

/** 后端校验错误（422）的结构，取第一条转成人话展示 */
interface ValidationErrorBody {
  detail: Array<{ msg: string; loc: (string | number)[] }>
}

async function readErrorDetail(response: Response): Promise<string> {
  const text = await response.text().catch(() => '')
  if (!text) return response.statusText

  try {
    const body = JSON.parse(text) as { detail?: string } | ValidationErrorBody
    const detail = body.detail
    if (typeof detail === 'string') return detail
    if (Array.isArray(detail) && detail.length > 0) return detail[0].msg
  } catch {
    // 非 JSON 响应，原样返回
  }
  return text
}

/**
 * 全站唯一的请求出口。集中在这里是为了让鉴权头、错误语义、
 * 401 清理只有一处定义，后续加 token 刷新时不必翻遍调用点。
 */
export async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = tokenStore.get()

  const response = await fetch(`${API_PREFIX}${path}`, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...init.headers,
    },
  })

  if (!response.ok) {
    // token 失效就地清理，避免后续请求继续带着废 token 反复触发 401
    if (response.status === 401) {
      tokenStore.clear()
    }
    throw new ApiError(response.status, await readErrorDetail(response))
  }

  if (response.status === 204) {
    return undefined as T
  }

  return (await response.json()) as T
}
