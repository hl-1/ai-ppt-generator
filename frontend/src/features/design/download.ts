import { useState } from 'react'
import { ApiError } from '@/api/client'
import { tokenStore } from '@/features/auth/token'

const FILENAME_PATTERN = /filename\*=UTF-8''([^;]+)/i

function filenameFromResponse(response: Response, fallback: string): string {
  const disposition = response.headers.get('content-disposition') ?? ''
  const matched = FILENAME_PATTERN.exec(disposition)
  return matched ? decodeURIComponent(matched[1]) : fallback
}

/**
 * 文件下载走 fetch 而非直接跳转链接，是因为需要带上鉴权头，
 * 且失败时要能读到后端的错误信息，而不是让浏览器打开一个错误页。
 */
export function useFileDownload() {
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const download = async (path: string, fallbackName: string) => {
    setPending(true)
    setError(null)

    const token = tokenStore.get()
    try {
      const response = await fetch(`/api/v1${path}`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      })
      if (!response.ok) {
        throw new ApiError(response.status, await response.text())
      }

      const blob = await response.blob()
      const url = URL.createObjectURL(blob)
      const anchor = document.createElement('a')
      anchor.href = url
      anchor.download = filenameFromResponse(response, fallbackName)
      anchor.click()
      URL.revokeObjectURL(url)
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.detail : '导出失败，请稍后重试')
    } finally {
      setPending(false)
    }
  }

  return { download, pending, error }
}
