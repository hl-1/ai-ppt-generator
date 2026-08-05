import { useEffect, useId, useRef, useState } from 'react'
import { useSlideLayouts, useSwitchSlideLayout } from '@/features/deck/api'
import type { DeckSlide, LayoutCandidate } from '@/features/deck/types'
import { errorMessage } from '@/lib/errors'
import { cn } from '@/lib/utils'

export function LayoutSwitcher({
  projectId,
  slide,
  disabled,
}: {
  projectId: string
  slide: DeckSlide
  disabled?: boolean
}) {
  const [open, setOpen] = useState(false)
  const [activeIndex, setActiveIndex] = useState(0)
  const listId = useId()
  const rootRef = useRef<HTMLDivElement>(null)
  const triggerRef = useRef<HTMLButtonElement>(null)
  const optionRefs = useRef<Array<HTMLButtonElement | null>>([])
  const layouts = useSlideLayouts(projectId, slide.id, open)
  const switchLayout = useSwitchSlideLayout(projectId, slide.id)
  const options = layouts.data ?? []

  useEffect(() => {
    if (!open) return
    const onPointer = (event: MouseEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) {
        setOpen(false)
        triggerRef.current?.focus()
      }
    }
    document.addEventListener('mousedown', onPointer)
    return () => document.removeEventListener('mousedown', onPointer)
  }, [open])

  useEffect(() => {
    if (!open || !layouts.data?.length) return
    const list = layouts.data
    const current = list.findIndex((item) => item.current)
    const firstCompatible = list.findIndex((item) => item.compatible)
    const index = current >= 0 ? current : Math.max(0, firstCompatible)
    setActiveIndex(index)
    // 等选项挂载后再聚焦
    requestAnimationFrame(() => optionRefs.current[index]?.focus())
  }, [open, layouts.data])

  const close = () => {
    setOpen(false)
    triggerRef.current?.focus()
  }

  const select = (candidate: LayoutCandidate) => {
    if (!candidate.compatible || candidate.current || switchLayout.isPending) return
    switchLayout.mutate(
      { layout_id: candidate.layout_id, revision: slide.revision },
      { onSuccess: () => close() },
    )
  }

  const moveActive = (delta: number) => {
    if (options.length === 0) return
    let next = activeIndex
    for (let step = 0; step < options.length; step += 1) {
      next = (next + delta + options.length) % options.length
      if (options[next]?.compatible) break
    }
    setActiveIndex(next)
    optionRefs.current[next]?.focus()
  }

  return (
    <div ref={rootRef} className="relative">
      <button
        ref={triggerRef}
        type="button"
        disabled={disabled || switchLayout.isPending}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={listId}
        onClick={() => setOpen((value) => !value)}
        onKeyDown={(event) => {
          if (event.key === 'Escape' && open) {
            event.preventDefault()
            close()
            return
          }
          if (event.key === 'ArrowDown' || event.key === 'Enter' || event.key === ' ') {
            event.preventDefault()
            setOpen(true)
          }
        }}
        className="text-xs text-ink-muted transition-colors hover:text-accent disabled:opacity-40"
      >
        {switchLayout.isPending ? '切换中…' : '切换布局'}
      </button>

      {open && (
        <div
          id={listId}
          role="listbox"
          aria-label="可选布局"
          className="absolute top-full right-0 z-20 mt-2 w-64 border border-line bg-canvas py-1"
          onKeyDown={(event) => {
            if (event.key === 'Escape') {
              event.preventDefault()
              close()
            } else if (event.key === 'Tab') {
              event.preventDefault()
              moveActive(event.shiftKey ? -1 : 1)
            } else if (event.key === 'ArrowDown') {
              event.preventDefault()
              moveActive(1)
            } else if (event.key === 'ArrowUp') {
              event.preventDefault()
              moveActive(-1)
            } else if (event.key === 'Home') {
              event.preventDefault()
              const first = options.findIndex((item) => item.compatible)
              if (first >= 0) {
                setActiveIndex(first)
                optionRefs.current[first]?.focus()
              }
            } else if (event.key === 'End') {
              event.preventDefault()
              const last = [...options].reverse().findIndex((item) => item.compatible)
              if (last >= 0) {
                const index = options.length - 1 - last
                setActiveIndex(index)
                optionRefs.current[index]?.focus()
              }
            } else if (event.key === 'Enter' || event.key === ' ') {
              event.preventDefault()
              const candidate = options[activeIndex]
              if (candidate) select(candidate)
            }
          }}
        >
          {layouts.isPending && (
            <p className="px-3 py-2 text-xs text-ink-muted">正在加载布局…</p>
          )}
          {layouts.isError && (
            <p className="px-3 py-2 text-xs text-negative">布局列表加载失败</p>
          )}
          {options.map((candidate, index) => (
            <LayoutOption
              key={candidate.layout_id}
              ref={(node) => {
                optionRefs.current[index] = node
              }}
              candidate={candidate}
              active={index === activeIndex}
              onSelect={() => select(candidate)}
            />
          ))}
        </div>
      )}

      {switchLayout.isError && (
        <p role="alert" className="mt-1 max-w-48 text-right text-[11px] text-negative">
          {errorMessage(switchLayout.error)}
        </p>
      )}
    </div>
  )
}

function LayoutOption({
  ref,
  candidate,
  active,
  onSelect,
}: {
  ref?: (node: HTMLButtonElement | null) => void
  candidate: LayoutCandidate
  active: boolean
  onSelect: () => void
}) {
  const disabled = !candidate.compatible
  return (
    <button
      ref={ref}
      type="button"
      role="option"
      tabIndex={active ? 0 : -1}
      aria-selected={candidate.current}
      aria-disabled={disabled || undefined}
      disabled={disabled}
      onClick={onSelect}
      className={cn(
        'flex w-full flex-col gap-0.5 px-3 py-2 text-left transition-colors',
        disabled
          ? 'cursor-not-allowed opacity-45'
          : 'hover:bg-surface focus:bg-surface focus:outline-none',
        (candidate.current || active) && 'bg-surface',
      )}
    >
      <span className="flex items-baseline justify-between gap-3 text-xs">
        <span className="font-medium text-ink">{candidate.name}</span>
        {candidate.current && (
          <span className="text-[10px] tracking-[0.14em] text-accent uppercase">当前</span>
        )}
      </span>
      <span className="text-[11px] leading-relaxed text-ink-muted">{candidate.usage}</span>
      {disabled && candidate.reason && (
        <span className="text-[11px] leading-relaxed text-ink-soft">{candidate.reason}</span>
      )}
    </button>
  )
}
