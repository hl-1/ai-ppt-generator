import { useState } from 'react'
import { Button } from '@/components/ui/Button'
import { useSampleDeck } from '@/features/design/api'
import { useFileDownload } from '@/features/design/download'
import { cn } from '@/lib/utils'
import { getLayout, getTheme, themeList } from '@/render/design'
import { SlideView } from '@/render/SlideView'

export default function DeckPreviewPage() {
  const deck = useSampleDeck()
  const [themeId, setThemeId] = useState<string>(themeList[0].id)
  const [activeIndex, setActiveIndex] = useState(0)
  const exporter = useFileDownload()

  if (deck.isPending) {
    return <p className="py-24 text-sm text-ink-muted">正在载入示例文稿…</p>
  }

  if (deck.isError || !deck.data) {
    return (
      <p className="my-24 border-l-2 border-negative py-3 pl-4 text-sm text-ink-soft">
        无法载入示例文稿，请确认 API 已启动。
      </p>
    )
  }

  const theme = getTheme(themeId)
  const slides = deck.data.slides
  const activeSlide = slides[activeIndex] ?? slides[0]
  const activeLayout = getLayout(activeSlide.layout_id)

  return (
    <>
      <section className="flex flex-wrap items-end justify-between gap-6 border-b border-line py-10">
        <div>
          <p className="mb-3 text-xs tracking-[0.2em] text-accent uppercase">渲染基线</p>
          <h1 className="font-display text-[clamp(1.75rem,3.2vw,2.25rem)] leading-tight">
            {deck.data.title}
          </h1>
          <p className="mt-3 text-sm text-ink-muted">
            共 {slides.length} 页，覆盖全部 {new Set(slides.map((s) => s.layout_id)).size}{' '}
            种布局。切换主题只改变视觉，内容与页序保持不变。
          </p>
        </div>

        <div className="flex flex-col items-end gap-3">
          <div className="flex items-stretch gap-5">
            <div
              role="radiogroup"
              aria-label="主题"
              className="flex divide-x divide-line border border-line"
            >
              {themeList.map((item) => (
                <button
                  key={item.id}
                  role="radio"
                  aria-checked={item.id === themeId}
                  onClick={() => setThemeId(item.id)}
                  className={cn(
                    'px-4 text-sm transition-colors',
                    item.id === themeId
                      ? 'bg-ink text-canvas'
                      : 'text-ink-soft hover:bg-accent-soft hover:text-accent',
                  )}
                >
                  {item.name}
                </button>
              ))}
            </div>

            <Button
              variant="accent"
              disabled={exporter.pending}
              onClick={() =>
                exporter.download(
                  `/design/sample-deck/pptx?theme_id=${themeId}`,
                  `${deck.data.title}.pptx`,
                )
              }
            >
              {exporter.pending ? '正在导出…' : '导出 PPTX'}
            </Button>
          </div>
          {exporter.error && <p className="text-sm text-negative">{exporter.error}</p>}
        </div>
      </section>

      <div className="grid gap-10 py-10 lg:grid-cols-[168px_1fr]">
        <nav aria-label="页面列表" className="flex gap-3 overflow-x-auto lg:flex-col lg:overflow-visible">
          {slides.map((slide, index) => (
            <button
              key={slide.id}
              onClick={() => setActiveIndex(index)}
              aria-current={index === activeIndex}
              className={cn(
                'group flex w-40 shrink-0 flex-col gap-1.5 text-left lg:w-full',
                'transition-opacity',
                index === activeIndex ? 'opacity-100' : 'opacity-55 hover:opacity-100',
              )}
            >
              <span
                className={cn(
                  'block border',
                  index === activeIndex ? 'border-accent' : 'border-line',
                )}
              >
                <SlideView slide={slide} theme={theme} />
              </span>
              <span className="flex items-baseline gap-2 text-[11px] text-ink-muted">
                <span className="tabular-nums">{String(index + 1).padStart(2, '0')}</span>
                <span className="truncate">{getLayout(slide.layout_id).name}</span>
              </span>
            </button>
          ))}
        </nav>

        <div>
          <div className="border border-line shadow-[0_1px_2px_rgba(0,0,0,0.04)]">
            <SlideView slide={activeSlide} theme={theme} />
          </div>
          <dl className="mt-5 flex flex-wrap gap-x-10 gap-y-2 text-sm">
            <div className="flex gap-2">
              <dt className="text-ink-muted">布局</dt>
              <dd>{activeLayout.name}</dd>
            </div>
            <div className="flex gap-2">
              <dt className="text-ink-muted">适用</dt>
              <dd className="text-ink-soft">{activeLayout.usage}</dd>
            </div>
          </dl>
        </div>
      </div>
    </>
  )
}
