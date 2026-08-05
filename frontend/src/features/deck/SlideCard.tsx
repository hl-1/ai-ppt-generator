import { type ChangeEvent, useRef } from 'react'
import { useReplaceSlideImage, useRetrySlide } from '@/features/deck/api'
import {
  ACCEPTED_IMAGE,
  SLIDE_STATUS_LABEL,
  type DeckSlide,
  imageBlocks,
  toRenderSlide,
} from '@/features/deck/types'
import { errorMessage } from '@/lib/errors'
import { cn } from '@/lib/utils'
import { SlideView } from '@/render/SlideView'
import { CANVAS_HEIGHT_PT, CANVAS_WIDTH_PT, type Theme } from '@/render/types'

export function SlideCard({
  projectId,
  slide,
  theme,
}: {
  projectId: string
  slide: DeckSlide
  theme: Theme
}) {
  const retry = useRetrySlide(projectId)
  const warnings = slide.issues.filter((issue) => issue.severity === 'warning')
  const settled = slide.status === 'ready' || slide.status === 'failed'
  const images = imageBlocks(slide)

  return (
    <li className="flex flex-col">
      <div
        className={cn(
          'border',
          slide.status === 'ready' ? 'border-line' : 'border-dashed border-line-strong',
          slide.status === 'failed' && 'border-solid border-negative/40',
        )}
        style={{ aspectRatio: `${CANVAS_WIDTH_PT} / ${CANVAS_HEIGHT_PT}` }}
      >
        {slide.status === 'ready' ? (
          <SlideView slide={toRenderSlide(slide)} theme={theme} />
        ) : (
          <SlidePlaceholder status={slide.status} error={slide.error} />
        )}
      </div>

      <div className="mt-4 flex items-start justify-between gap-4">
        <div className="min-w-0">
          <p className="truncate text-sm font-medium">
            <span className="mr-3 text-line-strong tabular-nums">
              {String(slide.position).padStart(2, '0')}
            </span>
            {slide.title}
          </p>
          <p className="mt-1 text-xs text-ink-muted">
            {SLIDE_STATUS_LABEL[slide.status]}
            {slide.status === 'ready' && warnings.length > 0 && (
              <span className="ml-3 text-warning">{warnings.length} 处内容偏长</span>
            )}
          </p>
          {/* 图库授权要求在使用处标注作者。署名放在编辑界面而不是页面里，
              既满足要求，也不侵占 PPT 的版面 */}
          {images.map(
            (block) =>
              block.credit && (
                <p key={block.id} className="mt-1 text-[11px] text-ink-muted">
                  {block.credit}
                </p>
              ),
          )}
        </div>

        <div className="flex shrink-0 flex-col items-end gap-2">
          {settled && (
            <button
              type="button"
              disabled={retry.isPending}
              onClick={() => retry.mutate(slide.id)}
              className="text-xs text-ink-muted transition-colors hover:text-accent disabled:opacity-40"
            >
              重新生成
            </button>
          )}
          {slide.status === 'ready' &&
            images.map((block, index) => (
              <ReplaceImageButton
                key={block.id}
                projectId={projectId}
                slide={slide}
                blockId={block.id}
                label={images.length > 1 ? `换图 ${index + 1}` : '换图'}
              />
            ))}
        </div>
      </div>
    </li>
  )
}

function ReplaceImageButton({
  projectId,
  slide,
  blockId,
  label,
}: {
  projectId: string
  slide: DeckSlide
  blockId: string
  label: string
}) {
  const inputRef = useRef<HTMLInputElement>(null)
  const replace = useReplaceSlideImage(projectId)

  const pick = (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    // 清空，否则连续选择同一个文件不会再触发 change
    event.target.value = ''
    if (file) replace.mutate({ slideId: slide.id, blockId, revision: slide.revision, file })
  }

  return (
    <>
      <button
        type="button"
        disabled={replace.isPending}
        onClick={() => inputRef.current?.click()}
        className="text-xs text-ink-muted transition-colors hover:text-accent disabled:opacity-40"
      >
        {replace.isPending ? '上传中…' : label}
      </button>
      <input
        ref={inputRef}
        type="file"
        accept={ACCEPTED_IMAGE}
        onChange={pick}
        aria-label={`${label}（PNG、JPEG 或 WebP）`}
        className="sr-only"
      />
      {replace.isError && (
        <span className="max-w-40 text-right text-[11px] text-negative">
          {errorMessage(replace.error, '换图失败')}
        </span>
      )}
    </>
  )
}

function SlidePlaceholder({
  status,
  error,
}: {
  status: DeckSlide['status']
  error: string | null
}) {
  if (status === 'failed') {
    return (
      <div className="flex h-full flex-col justify-end bg-negative/[0.04] p-7">
        <p className="text-xs leading-relaxed text-negative">{error ?? '生成失败'}</p>
      </div>
    )
  }

  const pulse = status === 'generating'
  return (
    <div className="flex h-full flex-col justify-end gap-3 bg-surface p-7">
      {/* 骨架按正文页的真实节奏排布，等待时的画面不会与最终结果割裂 */}
      <div className={cn('h-2 w-1/2', pulse ? 'animate-pulse bg-accent/40' : 'bg-line-strong')} />
      <div className={cn('h-1.5 w-4/5 bg-line', pulse && 'animate-pulse')} />
      <div className={cn('h-1.5 w-3/5 bg-line', pulse && 'animate-pulse')} />
    </div>
  )
}
