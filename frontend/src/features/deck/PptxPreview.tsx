import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { request, requestBinary } from '@/api/client'
import { Button } from '@/components/ui/Button'
import { errorMessage } from '@/lib/errors'
import type { Deck } from './types'

type Preview = {
  status: 'missing' | 'queued' | 'rendering' | 'ready' | 'failed' | 'unavailable'
  fingerprint: string
  page_count: number
  message?: string
}

export function PptxPreview({ projectId, deck }: { projectId: string; deck: Deck }) {
  const client = useQueryClient()
  const key = ['pptx-preview', projectId, deck] as const
  const [page, setPage] = useState(1)
  const query = useQuery({
    queryKey: key,
    queryFn: () => request<Preview>(`/projects/${projectId}/deck/preview`),
    refetchInterval: (q) => ['queued', 'rendering'].includes(q.state.data?.status ?? '') ? 2000 : false,
  })
  const generate = useMutation({
    mutationFn: () => request<Preview>(`/projects/${projectId}/deck/preview`, { method: 'POST' }),
    onSuccess: (result) => { client.setQueryData(key, result); setPage(1) },
  })
  const result = query.data
  const busy = generate.isPending || result?.status === 'queued' || result?.status === 'rendering'
  const count = result?.page_count ?? 0
  const selected = Math.max(1, Math.min(page, count))
  return (
    <section className="rounded-xl border border-line p-4">
      <div className="flex items-center justify-between gap-3">
        <h3 className="text-sm font-semibold">实际 PPTX 预览</h3>
        <Button size="sm" disabled={busy || result?.status === 'unavailable'} onClick={() => generate.mutate()}>
          {busy ? '正在生成…' : result?.status === 'ready' ? '检查当前版本' : '生成预览'}
        </Button>
      </div>
      <p className="mt-2 text-xs text-ink-muted">
        {result?.message ?? '预览由导出的 PPTX 转换生成。请检查文字遮挡、图表标签和信息密度。'}
      </p>
      {(query.error || generate.error) && <p role="alert" className="mt-2 text-xs text-negative">
        {errorMessage(query.error ?? generate.error)}
      </p>}
      {result?.status === 'ready' && count > 0 && <>
        <PreviewImage projectId={projectId} fingerprint={result.fingerprint} page={selected} />
        <div className="mt-3 flex items-center justify-between text-xs text-ink-muted">
          <button disabled={selected <= 1} onClick={() => setPage(selected - 1)}>上一页</button>
          <span>第 {selected} / {count} 页 · 当前版本</span>
          <button disabled={selected >= count} onClick={() => setPage(selected + 1)}>下一页</button>
        </div>
      </>}
    </section>
  )
}

function PreviewImage({ projectId, fingerprint, page }: { projectId: string; fingerprint: string; page: number }) {
  const [url, setUrl] = useState('')
  const [error, setError] = useState('')
  useEffect(() => {
    let disposed = false
    let objectUrl = ''
    setUrl(''); setError('')
    void requestBinary(`/projects/${projectId}/deck/preview/${fingerprint}/pages/${page}`)
      .then((r) => r.blob()).then((blob) => {
        if (disposed) return
        objectUrl = URL.createObjectURL(blob)
        setUrl(objectUrl)
      }).catch((e) => { if (!disposed) setError(errorMessage(e)) })
    return () => { disposed = true; if (objectUrl) URL.revokeObjectURL(objectUrl) }
  }, [projectId, fingerprint, page])
  if (error) return <p role="alert" className="mt-3 text-xs text-negative">{error}</p>
  return url ? <img src={url} alt={`导出文件第 ${page} 页`} className="mt-3 w-full border border-line" />
    : <p className="mt-3 text-xs">正在读取页面…</p>
}
