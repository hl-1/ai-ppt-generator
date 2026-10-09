import {
  Check, ImageIcon, Loader2, LockKeyhole, LockKeyholeOpen, Plus, RefreshCw,
  Search, Sparkles, Upload,
} from 'lucide-react'
import { type ChangeEvent, useEffect, useRef, useState } from 'react'
import {
  useAddSlideImage, useImageAction, useImageSearch, useReplaceSlideImage,
} from '@/features/deck/api'
import { ACCEPTED_IMAGE, type DeckSlide, imageBlocks } from '@/features/deck/types'
import { errorMessage } from '@/lib/errors'
import type { ImageBlock } from '@/render/types'
import { cn } from '@/lib/utils'
import { getLayout } from '@/render/design'
import { solve } from '@/render/flexLayout'
import { CANVAS_WIDTH_PT, CANVAS_HEIGHT_PT } from '@/render/types'

const SOURCE_LABEL: Record<ImageBlock['source'], string> = {
  generated: 'AI 生成',
  stock: '图库',
  upload: '手动上传',
  placeholder: '占位图',
}

export function ImagePanel({
  projectId,
  slide,
  disabled,
}: {
  projectId: string
  slide: DeckSlide
  disabled?: boolean
}) {
  const images = imageBlocks(slide)
  const add = useAddSlideImage(projectId)

  if (images.length === 0) {
    return (
      <div className="rounded-lg border border-dashed border-line-strong px-4 py-6 text-center">
        <ImageIcon className="mx-auto mb-2 size-4 text-ink-muted" />
        <p className="text-[13px] text-ink-muted">这一页的版式里没有图片位</p>
        <button type="button" disabled={disabled || add.isPending}
          onClick={() => add.mutate({ slideId: slide.id, revision: slide.revision, subject: slide.title })}
          className="mx-auto mt-3 flex items-center gap-2 rounded-lg border border-line px-3 py-2 text-sm disabled:opacity-50">
          <Plus className="size-4" />添加配图
        </button>
        {add.isError && <p role="alert" className="mt-2 text-xs text-negative">{errorMessage(add.error)}</p>}
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-4">
      {images.map((block, index) => (
        <ImageSlot
          key={`${slide.id}-${block.id}`}
          projectId={projectId}
          slide={slide}
          block={block}
          label={images.length > 1 ? `图片 ${index + 1}` : '图片'}
          disabled={disabled}
        />
      ))}
      {images.length < 3 && <button type="button" disabled={disabled || add.isPending}
        onClick={() => add.mutate({ slideId: slide.id, revision: slide.revision, subject: slide.title })}
        className="flex items-center justify-center gap-2 rounded-lg border border-line py-2 text-sm disabled:opacity-50">
        <Plus className="size-4" />添加配图
      </button>}
      {add.isError && <p role="alert" className="text-xs text-negative">{errorMessage(add.error)}</p>}
    </div>
  )
}

function ImageSlot({
  projectId,
  slide,
  block,
  label,
  disabled,
}: {
  projectId: string
  slide: DeckSlide
  block: ImageBlock
  label: string
  disabled?: boolean
}) {
  const inputRef = useRef<HTMLInputElement>(null)
  const replace = useReplaceSlideImage(projectId)
  const search = useImageSearch(projectId)
  const action = useImageAction(projectId)
  const [mode, setMode] = useState<'stock' | 'generated' | 'upload'>('stock')
  const [query, setQuery] = useState(block.image_plan?.subject ?? block.alt)
  const rect = slide.layout_tree ? solve(slide.layout_tree).find((item) => item.block_id === block.id)?.rect
    : getLayout(slide.layout_id).slots.find((slot) => slot.id === block.slot_id)?.rect
  const aspectRatio = rect && rect.h > 0 ? (rect.w * CANVAS_WIDTH_PT) / (rect.h * CANVAS_HEIGHT_PT) : 16 / 9
  const [now, setNow] = useState(() => Date.now() / 1000)
  useEffect(() => {
    if (block.image_status !== 'queued') return
    const timer = window.setInterval(() => setNow(Date.now() / 1000), 2000)
    return () => window.clearInterval(timer)
  }, [block.image_status])
  const queued = block.image_status === 'queued'
    && now - (block.image_job_started_at ?? 0) < 15 * 60
  const busy = disabled || replace.isPending || action.isPending
  const apply = (searchId: string, candidateId: string) => action.mutate({
    action: 'apply', slideId: slide.id, blockId: block.id, revision: slide.revision,
    search_id: searchId, candidate_id: candidateId,
  })
  const generate = (source: 'auto' | 'stock' | 'generated') => action.mutate({
    action: 'generate', slideId: slide.id, blockId: block.id, revision: slide.revision,
    query, source,
  })

  const pick = (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    // 清空，否则连续选择同一个文件不会再触发 change
    event.target.value = ''
    if (file) {
      replace.mutate({ slideId: slide.id, blockId: block.id, revision: slide.revision, file })
    }
  }

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center justify-between gap-2">
        <span className="text-[13px] font-medium">{label}</span>
        <div className="flex items-center gap-2">
          <span className="text-xs text-ink-muted">{SOURCE_LABEL[block.source]}</span>
          <button type="button" disabled={busy} title={block.locked ? '解锁图片' : '锁定图片'}
            aria-label={block.locked ? '解锁图片' : '锁定图片'} aria-pressed={block.locked}
            onClick={() => action.mutate({ action: 'lock', locked: !block.locked,
              slideId: slide.id, blockId: block.id, revision: slide.revision })}
            className="grid size-8 place-items-center rounded-md hover:bg-surface-soft disabled:opacity-50">
            {block.locked ? <LockKeyhole className="size-4" /> : <LockKeyholeOpen className="size-4" />}
          </button>
        </div>
      </div>

      <div className="overflow-hidden rounded-lg border border-line bg-surface-soft">
        {block.url ? (
          <img src={block.url} alt={block.alt} className="aspect-video w-full object-cover" />
        ) : (
          <div className="grid aspect-video place-items-center text-ink-muted">
            <ImageIcon className="size-5" />
          </div>
        )}
      </div>

      <div aria-live="polite" className="text-xs text-ink-muted">
        {queued ? <span className="flex items-center gap-1.5"><Loader2 className="size-3 animate-spin" />正在配图</span>
          : block.image_error ? <span className="text-negative">{block.image_error}</span>
          : block.image_status === 'queued' ? '图片任务已超时，可重新尝试'
          : block.locked ? '图片已锁定' : null}
      </div>

      <div role="tablist" aria-label={`${label}图源`} className="grid grid-cols-3 border-b border-line text-xs">
        {([{ id: 'stock', text: '图库', Icon: Search }, { id: 'generated', text: 'AI 插图', Icon: Sparkles },
          { id: 'upload', text: '上传', Icon: Upload }] as const).map(({ id, text, Icon }) => (
          <button key={id} id={`image-tab-${block.id}-${id}`} type="button" role="tab"
            aria-selected={mode === id} tabIndex={mode === id ? 0 : -1}
            aria-controls={`image-tools-${block.id}`} onClick={() => setMode(id)}
            onKeyDown={(event) => {
              if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') return
              event.preventDefault()
              const modes = ['stock', 'generated', 'upload'] as const
              const next = (modes.indexOf(mode) + (event.key === 'ArrowRight' ? 1 : 2)) % 3
              setMode(modes[next])
              event.currentTarget.parentElement?.querySelectorAll<HTMLButtonElement>('[role="tab"]')[next]?.focus()
            }}
            className={cn('flex min-h-10 items-center justify-center gap-1 border-b-2 px-1 py-2',
              mode === id ? 'border-accent text-accent' : 'border-transparent text-ink-muted')}>
            <Icon className="size-3.5" />{text}
          </button>
        ))}
      </div>

      <div id={`image-tools-${block.id}`} role="tabpanel"
        aria-labelledby={`image-tab-${block.id}-${mode}`} className="flex flex-col gap-2">
        {mode !== 'upload' && <form onSubmit={(event) => {
          event.preventDefault()
          if (!query.trim() || busy || search.isPending
            || (mode === 'generated' && (queued || block.locked))) return
          if (mode === 'stock') search.mutate({ query, aspect_ratio: aspectRatio })
          else generate('generated')
        }} className="flex items-start gap-2">
          <textarea aria-label={mode === 'stock' ? '配图检索关键词' : 'AI 插图描述'}
            value={query} rows={2} maxLength={120} disabled={busy || search.isPending}
            onChange={(event) => { setQuery(event.target.value); search.reset() }}
            className="min-w-0 flex-1 resize-y rounded-md border border-line bg-surface px-2 py-1.5 text-[13px]" />
          <button type="submit" aria-label={mode === 'stock' ? '搜索图片' : '生成 AI 插图'}
            title={mode === 'stock' ? '搜索图片' : '生成 AI 插图'}
            disabled={busy || !query.trim() || search.isPending || (mode === 'generated' && (queued || block.locked))}
            className="grid size-9 shrink-0 place-items-center rounded-md border border-line hover:bg-surface-soft disabled:opacity-50">
            {search.isPending || action.isPending ? <Loader2 className="size-4 animate-spin" />
              : mode === 'stock' ? <Search className="size-4" /> : <Sparkles className="size-4" />}
          </button>
        </form>}
        {mode === 'stock' && search.data && <>
          {search.data.candidates.length === 0 && <p className="text-xs text-ink-muted">没有找到候选图片</p>}
          <div className="grid grid-cols-2 gap-2">
            {search.data.candidates.map((candidate) => <div key={candidate.id} className="min-w-0">
              <button type="button" disabled={busy} aria-label={`选用图片：${candidate.description || candidate.id}`}
                title={candidate.match_reason} onClick={() => apply(search.data.search_id, candidate.id)}
                className={cn('relative block aspect-video w-full overflow-hidden rounded-md border',
                  candidate.id === block.image_asset_id ? 'border-accent' : 'border-line')}>
                <img src={candidate.thumbnail_url} alt={candidate.description || '图库候选'}
                  className="h-full w-full object-cover" loading="lazy" />
                {candidate.id === block.image_asset_id && <Check className="absolute right-1 top-1 size-5 rounded bg-surface p-0.5 text-accent" />}
              </button>
              <p className="mt-1 break-words text-[11px] text-ink-muted">{candidate.match_reason}</p>
              <a href={candidate.credit_url} target="_blank" rel="noreferrer"
                className="mt-0.5 block break-words text-[11px] text-ink-muted underline">{candidate.credit}</a>
            </div>)}
          </div>
        </>}
        {mode !== 'upload' && <button type="button" disabled={busy || queued || block.locked}
          onClick={() => generate(mode === 'stock' ? 'stock' : 'generated')}
          className="flex items-center justify-center gap-1.5 rounded-md border border-line py-2 text-xs disabled:opacity-50">
          <RefreshCw className="size-3.5" />重新配图
        </button>}

      {mode === 'upload' &&
      <button
        type="button"
        disabled={busy}
        onClick={() => inputRef.current?.click()}
        className="flex items-center justify-center gap-1.5 rounded-md border border-line py-2 text-[13px] text-ink-soft transition-colors hover:border-line-strong hover:text-ink disabled:opacity-50"
      >
        <Upload className="size-3.5" />
        {replace.isPending ? '上传中…' : '替换图片'}
      </button>}
      </div>
      <input
        ref={inputRef}
        type="file"
        accept={ACCEPTED_IMAGE}
        onChange={pick}
        aria-label={`${label}：上传 PNG、JPEG 或 WebP`}
        className="sr-only"
      />

      {/* 图库授权要求标注作者：放在编辑侧栏而不是页面里，既满足要求也不占版面 */}
      {block.credit && <p className="break-words text-xs leading-relaxed text-ink-muted">
        {block.credit_url ? <a href={block.credit_url} target="_blank" rel="noreferrer" className="underline">{block.credit}</a> : block.credit}
      </p>}
      {(replace.isError || search.isError || action.isError) && (
        <p role="alert" className="text-xs text-negative">
          {errorMessage(replace.error ?? search.error ?? action.error, '图片处理失败')}
        </p>
      )}
    </div>
  )
}
