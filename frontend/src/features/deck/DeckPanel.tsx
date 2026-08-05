import { Button } from '@/components/ui/Button'
import { useCancelDeck, useDeck, useGenerateDeck, useRetrySlide } from '@/features/deck/api'
import { SLIDE_STATUS_LABEL, type DeckSlide, toRenderSlide } from '@/features/deck/types'
import { useDeckProgress } from '@/features/deck/useDeckProgress'
import { errorMessage } from '@/lib/errors'
import { cn } from '@/lib/utils'
import { getTheme } from '@/render/design'
import { SlideView } from '@/render/SlideView'
import { CANVAS_HEIGHT_PT, CANVAS_WIDTH_PT, type Theme } from '@/render/types'

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
  const deck = deckQuery.data
  const generating = deck?.status === 'generating'
  const progress = useDeckProgress(projectId, outlineConfirmed && generating)
  const theme = getTheme(themeId)

  const started = (deck?.total ?? 0) > 0
  const actionError = generate.error ?? cancel.error

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
            message={progress.event?.message}
            connectionError={progress.connectionError}
          />

          <ol className="mt-12 grid gap-10 md:grid-cols-2 xl:grid-cols-3">
            {deck.slides.map((slide) => (
              <SlideCard key={slide.id} projectId={projectId} slide={slide} theme={theme} />
            ))}
          </ol>
        </>
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
          分成两条会让人误以为总进度不到 100% */}
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

function SlideCard({
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
        </div>
        {settled && (
          <button
            type="button"
            disabled={retry.isPending}
            onClick={() => retry.mutate(slide.id)}
            className="shrink-0 text-xs text-ink-muted transition-colors hover:text-accent disabled:opacity-40"
          >
            重新生成
          </button>
        )}
      </div>
    </li>
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
