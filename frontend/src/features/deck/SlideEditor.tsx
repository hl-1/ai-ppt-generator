import { useEffect, useId, useRef } from 'react'
import { Button } from '@/components/ui/Button'
import { AiEditPanel } from '@/features/deck/AiEditPanel'
import { LayoutSwitcher } from '@/features/deck/LayoutSwitcher'
import type { DeckSlide } from '@/features/deck/types'
import { toRenderSlide } from '@/features/deck/types'
import { useSlideSaveQueue } from '@/features/deck/useSlideSaveQueue'
import { SlideView } from '@/render/SlideView'
import type { Theme } from '@/render/types'

export function SlideEditor({
  projectId,
  slide,
  theme,
  onClose,
}: {
  projectId: string
  slide: DeckSlide
  theme: Theme
  onClose: () => void
}) {
  const titleId = useId()
  const closeRef = useRef<HTMLButtonElement>(null)
  const onCloseRef = useRef(onClose)
  const statusRef = useRef<'idle' | 'saving' | 'saved' | 'conflict' | 'error'>('idle')
  const { commit, status, error, refresh } = useSlideSaveQueue(projectId, slide.id)
  const lockedCount = slide.blocks.filter((block) => block.locked).length
  const warnings = slide.issues.filter((issue) => issue.severity === 'warning')
  onCloseRef.current = onClose
  statusRef.current = status

  useEffect(() => {
    closeRef.current?.focus()
    const previous = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== 'Escape' || statusRef.current === 'saving') return
      // 字段内 Esc 只撤销草稿，不关掉编辑器
      if ((event.target as HTMLElement | null)?.isContentEditable) return
      onCloseRef.current()
    }
    document.addEventListener('keydown', onKeyDown)
    return () => {
      document.body.style.overflow = previous
      document.removeEventListener('keydown', onKeyDown)
    }
  }, [])

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby={titleId}
      className="fixed inset-0 z-40 flex flex-col bg-canvas"
    >
      <header className="flex flex-wrap items-center justify-between gap-4 border-b border-line px-6 py-4 md:px-10">
        <div className="min-w-0">
          <p className="mb-1 text-[10px] tracking-[0.2em] text-accent uppercase">单页编辑</p>
          <h2 id={titleId} className="truncate font-display text-2xl">
            {slide.title}
          </h2>
          <p className="mt-1 text-xs text-ink-muted">
            直接在页面上改文字，停止输入后自动保存
            {lockedCount > 0 && (
              <span className="ml-3 text-ink-soft">
                {lockedCount} 处已人工修改，AI 不会覆盖
              </span>
            )}
            {warnings.length > 0 && (
              <span className="ml-3 text-warning">{warnings.length} 处内容偏长</span>
            )}
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-4">
          <SaveStatus status={status} error={error} onRefresh={refresh} />
          <LayoutSwitcher projectId={projectId} slide={slide} />
          <Button ref={closeRef} variant="ghost" onClick={onClose}>
            完成
          </Button>
        </div>
      </header>

      <div className="flex min-h-0 flex-1 flex-col md:flex-row">
        <div className="flex min-h-0 flex-1 flex-col">
          <div className="flex flex-1 items-center justify-center overflow-auto px-6 py-8 md:px-10">
            <div className="w-full max-w-5xl border border-line">
              <SlideView
                slide={toRenderSlide(slide)}
                theme={theme}
                editable={status !== 'conflict'}
                onCommit={commit}
              />
            </div>
          </div>
          <footer className="border-t border-line px-6 py-3 text-[11px] text-ink-muted md:px-10">
            Enter 提交单行字段 · Esc 撤销当前字段修改 · 色点标记表示该块已锁定
          </footer>
        </div>
        <AiEditPanel projectId={projectId} slide={slide} />
      </div>
    </div>
  )
}

function SaveStatus({
  status,
  error,
  onRefresh,
}: {
  status: 'idle' | 'saving' | 'saved' | 'conflict' | 'error'
  error: string | null
  onRefresh: () => void
}) {
  if (status === 'idle') return null

  if (status === 'saving') {
    return <span className="text-xs text-ink-muted">保存中…</span>
  }
  if (status === 'saved') {
    return <span className="text-xs text-accent">已保存</span>
  }
  if (status === 'conflict') {
    return (
      <span className="flex items-center gap-3 text-xs text-negative">
        {error ?? '页面已被其他操作更新'}
        <button
          type="button"
          onClick={onRefresh}
          className="text-ink-muted underline-offset-2 hover:text-accent hover:underline"
        >
          刷新
        </button>
      </span>
    )
  }
  return (
    <span role="alert" className="text-xs text-negative">
      {error ?? '保存失败'}
    </span>
  )
}
