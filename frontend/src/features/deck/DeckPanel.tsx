import { type DragEvent, useState } from 'react'
import { Button } from '@/components/ui/Button'
import {
  useCancelDeck,
  useDeck,
  useGenerateDeck,
  useReorderSlides,
} from '@/features/deck/api'
import { QualityExportPanel } from '@/features/deck/QualityExportPanel'
import { SlideCard } from '@/features/deck/SlideCard'
import { SlideEditor } from '@/features/deck/SlideEditor'
import { useDeckProgress } from '@/features/deck/useDeckProgress'
import { errorMessage } from '@/lib/errors'
import { getTheme } from '@/render/design'

export function DeckPanel({
  projectId,
  themeId,
  outlineConfirmed,
}: {
  projectId: string
  themeId: string
  outlineConfirmed: boolean
}) {
  const deckQuery = useDeck(projectId, outlineConfirmed)
  const generate = useGenerateDeck(projectId)
  const cancel = useCancelDeck(projectId)
  const reorder = useReorderSlides(projectId)
  const deck = deckQuery.data
  const generating = deck?.status === 'generating'
  const progress = useDeckProgress(projectId, outlineConfirmed && generating)
  const theme = getTheme(themeId)
  const [editingSlideId, setEditingSlideId] = useState<string | null>(null)
  const [dragId, setDragId] = useState<string | null>(null)
  const [dragOverId, setDragOverId] = useState<string | null>(null)

  const started = (deck?.total ?? 0) > 0
  const actionError = generate.error ?? cancel.error ?? reorder.error
  const editingSlide = deck?.slides.find((slide) => slide.id === editingSlideId)

  const moveSlide = (index: number, direction: -1 | 1) => {
    if (!deck || generating || reorder.isPending) return
    const target = index + direction
    if (target < 0 || target >= deck.slides.length) return
    const ids = deck.slides.map((slide) => slide.id)
    ;[ids[index], ids[target]] = [ids[target]!, ids[index]!]
    reorder.mutate(ids)
  }

  const onCardDragStart = (slideId: string, event: DragEvent<HTMLLIElement>) => {
    if (generating) {
      event.preventDefault()
      return
    }
    event.dataTransfer.effectAllowed = 'move'
    event.dataTransfer.setData('text/plain', slideId)
    setDragId(slideId)
  }

  const onCardDrop = (targetId: string, event: DragEvent<HTMLLIElement>) => {
    event.preventDefault()
    const sourceId = dragId ?? event.dataTransfer.getData('text/plain')
    setDragId(null)
    setDragOverId(null)
    if (!deck || !sourceId || sourceId === targetId || generating) return
    const ids = deck.slides.map((slide) => slide.id)
    const from = ids.indexOf(sourceId)
    const to = ids.indexOf(targetId)
    if (from < 0 || to < 0) return
    ids.splice(from, 1)
    ids.splice(to, 0, sourceId)
    reorder.mutate(ids)
  }

  return (
    <section className="border-t border-line py-16">
      <div className="mb-10 flex flex-wrap items-end justify-between gap-8">
        <div>
          <p className="mb-3 text-xs tracking-[0.2em] text-accent uppercase">页面生成</p>
          <h2 className="font-display text-3xl">每一页单独生成，单独失败，单独重试。</h2>
          <p className="mt-3 max-w-2xl text-sm leading-relaxed text-ink-muted">
            页面按大纲并发生成，中途中断不会丢掉已完成的页；再点一次生成，只补没生成的那部分。
          </p>
        </div>

        {outlineConfirmed && (
          <div className="flex items-center gap-3">
            {generating ? (
              <Button variant="ghost" disabled={cancel.isPending} onClick={() => cancel.mutate()}>
                {cancel.isPending ? '正在取消…' : '取消生成'}
              </Button>
            ) : (
              <>
                {started && (
                  <Button
                    variant="ghost"
                    disabled={generate.isPending}
                    onClick={() => generate.mutate({ regenerateAll: true })}
                  >
                    全部重新生成
                  </Button>
                )}
                <Button
                  variant="accent"
                  disabled={generate.isPending || deck?.status === 'ready'}
                  onClick={() => generate.mutate({ regenerateAll: false })}
                >
                  {generate.isPending ? '正在提交…' : started ? '继续生成' : '生成全部页面'}
                </Button>
              </>
            )}
          </div>
        )}
      </div>

      {!outlineConfirmed && (
        <p className="border border-dashed border-line-strong bg-surface px-8 py-10 text-sm text-ink-soft">
          确认大纲后即可开始生成页面。
        </p>
      )}

      {actionError && (
        <p role="alert" className="mb-6 text-sm text-negative">
          {errorMessage(actionError)}
        </p>
      )}

      {outlineConfirmed && deck && !started && (
        <p className="border border-dashed border-line-strong bg-surface px-8 py-10 text-sm text-ink-soft">
          还没有生成任何页面。
        </p>
      )}

      {outlineConfirmed && deck && started && (
        <>
          <DeckProgressBar
            ready={progress.event?.ready ?? deck.ready}
            failed={progress.event?.failed ?? deck.failed}
            total={progress.event?.total ?? deck.total}
            message={
              progress.event?.message ??
              (generating
                ? undefined
                : deck.status === 'ready'
                  ? '全部页面已生成'
                  : deck.status === 'partial'
                    ? '部分页面待继续生成'
                    : undefined)
            }
            connectionError={progress.connectionError}
          />

          <ol className="mt-12 grid gap-10 md:grid-cols-2 xl:grid-cols-3">
            {deck.slides.map((slide, index) => (
              <SlideCard
                key={slide.id}
                projectId={projectId}
                slide={slide}
                theme={theme}
                index={index}
                count={deck.slides.length}
                deckGenerating={generating}
                onEdit={() => setEditingSlideId(slide.id)}
                onMove={(direction) => moveSlide(index, direction)}
                onDragStart={(event) => onCardDragStart(slide.id, event)}
                onDragOver={(event) => {
                  if (generating || !dragId || dragId === slide.id) return
                  event.preventDefault()
                  setDragOverId(slide.id)
                }}
                onDrop={(event) => onCardDrop(slide.id, event)}
                onDragEnd={() => {
                  setDragId(null)
                  setDragOverId(null)
                }}
                dragging={dragId === slide.id}
                dragOver={dragOverId === slide.id}
              />
            ))}
          </ol>

          {!generating && (deck.status === 'ready' || deck.status === 'partial') && (
            <QualityExportPanel projectId={projectId} deck={deck} />
          )}
        </>
      )}

      {editingSlide && (
        <SlideEditor
          projectId={projectId}
          slide={editingSlide}
          theme={theme}
          onClose={() => setEditingSlideId(null)}
        />
      )}
    </section>
  )
}

function DeckProgressBar({
  ready,
  failed,
  total,
  message,
  connectionError,
}: {
  ready: number
  failed: number
  total: number
  message?: string
  connectionError: boolean
}) {
  const readyPercent = total ? (ready * 100) / total : 0
  const failedPercent = total ? (failed * 100) / total : 0

  return (
    <div className="border border-line bg-surface px-8 py-7">
      <div className="mb-4 flex flex-wrap items-baseline justify-between gap-4">
        <span className="text-sm font-medium">{message ?? '等待生成任务'}</span>
        <span className="font-display text-2xl tabular-nums">
          <span className="text-accent">{ready}</span>
          <span className="text-line-strong"> / {total}</span>
          {failed > 0 && <span className="ml-4 text-base text-negative">{failed} 页失败</span>}
        </span>
      </div>
      {/* 完成与失败共用一条进度条：失败也是"这一页已经有结论"，
          拆成两条会让人误以为总进度永远到不了 100% */}
      <div className="flex h-1 overflow-hidden bg-line">
        <div
          className="h-full bg-accent transition-[width] duration-500"
          style={{ width: `${readyPercent}%` }}
        />
        <div
          className="h-full bg-negative transition-[width] duration-500"
          style={{ width: `${failedPercent}%` }}
        />
      </div>
      {connectionError && (
        <p className="mt-3 text-xs text-ink-muted">进度连接暂时中断，正在自动重连…</p>
      )}
    </div>
  )
}
