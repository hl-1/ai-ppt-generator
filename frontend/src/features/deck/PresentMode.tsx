import { ChevronLeft, ChevronRight, X } from 'lucide-react'
import { useCallback, useEffect, useRef, useState } from 'react'
import { type DeckSlide, toRenderSlide } from '@/features/deck/types'
import { SlideView } from '@/render/SlideView'
import type { Theme } from '@/render/types'

/** 全屏放映：只做翻页与退出，不含演讲者备注 */
export function PresentMode({
  slides,
  theme,
  startIndex,
  onClose,
}: {
  slides: DeckSlide[]
  theme: Theme
  startIndex: number
  onClose: () => void
}) {
  const [index, setIndex] = useState(startIndex)
  const rootRef = useRef<HTMLDivElement>(null)
  const onCloseRef = useRef(onClose)
  onCloseRef.current = onClose

  const clamp = useCallback(
    (next: number) => Math.min(Math.max(next, 0), slides.length - 1),
    [slides.length],
  )

  useEffect(() => {
    // 全屏被浏览器策略拒绝时仍保持覆盖层放映，不打断用户
    void rootRef.current?.requestFullscreen?.().catch(() => {})

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'ArrowRight' || event.key === ' ' || event.key === 'PageDown') {
        event.preventDefault()
        setIndex((current) => Math.min(current + 1, slides.length - 1))
      } else if (event.key === 'ArrowLeft' || event.key === 'PageUp') {
        event.preventDefault()
        setIndex((current) => Math.max(current - 1, 0))
      } else if (event.key === 'Escape') {
        onCloseRef.current()
      }
    }

    document.addEventListener('keydown', onKeyDown)
    return () => {
      document.removeEventListener('keydown', onKeyDown)
      if (document.fullscreenElement) void document.exitFullscreen().catch(() => {})
    }
  }, [slides.length])

  const slide = slides[clamp(index)]
  if (!slide) return null

  return (
    <div ref={rootRef} className="fixed inset-0 z-[60] flex flex-col bg-[#0b0d12]">
      <div className="flex min-h-0 flex-1 items-center justify-center p-6">
        <div className="w-full max-w-[1600px] overflow-hidden rounded-lg shadow-slide">
          <SlideView slide={toRenderSlide(slide)} theme={theme} />
        </div>
      </div>

      <div className="flex items-center justify-center gap-3 pb-6 text-white/60">
        <button
          type="button"
          aria-label="上一页"
          disabled={index === 0}
          onClick={() => setIndex(clamp(index - 1))}
          className="grid size-9 place-items-center rounded-full transition-colors hover:bg-white/10 hover:text-white disabled:opacity-30"
        >
          <ChevronLeft className="size-5" />
        </button>
        <span className="min-w-16 text-center text-sm tabular-nums">
          {index + 1} / {slides.length}
        </span>
        <button
          type="button"
          aria-label="下一页"
          disabled={index === slides.length - 1}
          onClick={() => setIndex(clamp(index + 1))}
          className="grid size-9 place-items-center rounded-full transition-colors hover:bg-white/10 hover:text-white disabled:opacity-30"
        >
          <ChevronRight className="size-5" />
        </button>
        <button
          type="button"
          aria-label="退出放映"
          onClick={onClose}
          className="ml-4 grid size-9 place-items-center rounded-full transition-colors hover:bg-white/10 hover:text-white"
        >
          <X className="size-5" />
        </button>
      </div>
    </div>
  )
}
