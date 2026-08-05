import { useState } from 'react'
import { ApiError, requestBinary } from '@/api/client'
import { filenameFromDisposition, saveBlob } from '@/lib/download'
import { errorMessage } from '@/lib/errors'

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

    try {
      const response = await requestBinary(path)
      const blob = await response.blob()
      saveBlob(blob, filenameFromDisposition(response.headers.get('content-disposition'), fallbackName))
    } catch (cause) {
      setError(
        cause instanceof ApiError
          ? errorMessage(cause, '导出失败，请稍后重试')
          : '导出失败，请稍后重试',
      )
    } finally {
      setPending(false)
    }
  }

  return { download, pending, error }
}
