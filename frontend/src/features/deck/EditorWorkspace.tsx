import {
  AlertTriangle,
  Download,
  Image as ImageIcon,
  LayoutTemplate,
  Loader2,
  Minus,
  MoreHorizontal,
  Palette,
  Play,
  Plus,
  RefreshCw,
  RotateCw,
  Sparkles,
  Wand2,
} from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { WorkbenchHeader } from '@/components/WorkbenchHeader'
import { Button } from '@/components/ui/Button'
import {
  useCancelDeck,
  useDeck,
  useGenerateDeck,
  useReorderSlides,
  useRetrySlide,
} from '@/features/deck/api'
import { AiEditPanel } from '@/features/deck/AiEditPanel'
import { ChartDataEditor } from '@/features/deck/ChartDataEditor'
import { ElementToolbar } from '@/features/deck/ElementToolbar'
import { ExportDialog } from '@/features/deck/ExportDialog'
import { Filmstrip } from '@/features/deck/Filmstrip'
import { FlexEditLayer } from '@/features/deck/FlexEditLayer'
import { findLeafParent, setContainerPreset } from '@/features/deck/flexTree'
import { ImagePanel } from '@/features/deck/ImagePanel'
import { LayoutPanel } from '@/features/deck/LayoutPanel'
import { PresentMode } from '@/features/deck/PresentMode'
import { RelayoutDock } from '@/features/deck/RelayoutPanel'
import { ThemePanel } from '@/features/deck/ThemePanel'
import { type DeckSlide, toRenderSlide } from '@/features/deck/types'
import { useDeckProgress } from '@/features/deck/useDeckProgress'
import { registerSlideSaveHandlers } from '@/features/deck/slideSaveBridge'
import { type SaveStatus, useSlideSaveQueue } from '@/features/deck/useSlideSaveQueue'
import type { ProjectDetail } from '@/features/projects/types'
import { errorMessage } from '@/lib/errors'
import { cn } from '@/lib/utils'
import type { BlockStyle } from '@/render/blockStyle'
import type { FlexContainer } from '@/render/flexLayout'
import { SlideView } from '@/render/SlideView'
import { resolveTheme, type ThemeOverrides } from '@/render/themeOverrides'
import type { Slide, Theme } from '@/render/types'

type BlockSelection = { slideId: string; blockId: string }

type RailTab = 'ai' | 'theme' | 'layout' | 'image'

const RAIL_TABS: Array<{ tab: RailTab; label: string; icon: typeof Wand2 }> = [
  { tab: 'ai', label: 'AI 修改', icon: Wand2 },
  { tab: 'theme', label: '主题', icon: Palette },
  { tab: 'layout', label: '版式', icon: LayoutTemplate },
  { tab: 'image', label: '图片', icon: ImageIcon },
]

const ZOOM_STEPS = [0.6, 0.8, 1, 1.25, 1.6]

/**
 * 编辑工作台：生成中就能进来，完成一页看一页。
 * 所有高频动作（改文字、切页、AI、演示、导出）都不离开这一屏。
 */
export function EditorWorkspace({ project }: { project: ProjectDetail }) {
  const deckQuery = useDeck(project.id)
  const deck = deckQuery.data
  const slides = deck?.slides ?? []
  // deck.status 是主信号；project.status 只覆盖「已入队但页仍 pending / 页间空隙」。
  // deck 已 ready 时不再信过期的 project.generating，避免顶栏卡在「取消生成」。
  const generating =
    deck?.status === 'generating' ||
    (project.status === 'generating' &&
      (deck == null ||
        (deck.status !== 'ready' &&
          deck.slides.some(
            (slide) => slide.status === 'pending' || slide.status === 'generating',
          ))))
  const progress = useDeckProgress(project.id, generating)
  const theme = resolveTheme(
    project.theme_id,
    (project.theme_overrides ?? {}) as ThemeOverrides,
  )

  const generate = useGenerateDeck(project.id)
  const cancel = useCancelDeck(project.id)
  const reorder = useReorderSlides(project.id)

  const [activeId, setActiveId] = useState<string | null>(null)
  const [scrollRequest, setScrollRequest] = useState<{ id: string; nonce: number } | null>(null)
  const [selection, setSelection] = useState<BlockSelection | null>(null)
  const [rail, setRail] = useState<RailTab | null>(null)
  const [relayoutOpen, setRelayoutOpen] = useState(false)
  const [zoomIndex, setZoomIndex] = useState(1)
  const [presenting, setPresenting] = useState(false)
  const [exporting, setExporting] = useState(false)

  // 用 id 串做依赖：deck 每次轮询都会换掉数组身份，但选中页不该因此跳走
  const slideIdsKey = slides.map((slide) => slide.id).join('|')
  useEffect(() => {
    const ids = slideIdsKey ? slideIdsKey.split('|') : []
    setActiveId((current) => (current && ids.includes(current) ? current : (ids[0] ?? null)))
  }, [slideIdsKey])

  useEffect(() => {
    setSelection((current) => {
      if (!current) return null
      if (!slides.some((slide) => slide.id === current.slideId)) return null
      return current
    })
  }, [slideIdsKey])

  useEffect(() => {
    if (!activeId) return
    setSelection((current) =>
      current && current.slideId !== activeId ? null : current,
    )
  }, [activeId])

  useEffect(() => {
    setRelayoutOpen(false)
  }, [activeId])

  const focusSlide = (id: string) => {
    setActiveId(id)
    setScrollRequest({ id, nonce: Date.now() })
  }

  const active = slides.find((slide) => slide.id === activeId) ?? null
  const ready = progress.event?.ready ?? deck?.ready ?? 0
  const failed = progress.event?.failed ?? deck?.failed ?? 0
  const total = progress.event?.total ?? deck?.total ?? 0
  const actionError = generate.error ?? cancel.error ?? reorder.error

  return (
    <div className="flex h-screen flex-col overflow-hidden">
      <WorkbenchHeader
        title={project.title}
        meta={
          generating ? (
            <span className="flex shrink-0 items-center gap-1.5 rounded-full bg-accent-soft px-2.5 py-0.5 text-[11px] font-medium text-accent tabular-nums">
              <Loader2 className="size-3 animate-spin" />
              {ready} / {total} 页
            </span>
          ) : failed > 0 ? (
            <span className="flex shrink-0 items-center gap-1.5 rounded-full bg-negative/10 px-2.5 py-0.5 text-[11px] font-medium text-negative">
              <AlertTriangle className="size-3" />
              {failed} 页失败
            </span>
          ) : total > 0 ? (
            <span className="shrink-0 rounded-full bg-surface-soft px-2.5 py-0.5 text-[11px] font-medium text-ink-muted tabular-nums">
              {total} 页
            </span>
          ) : null
        }
      >
        {generating ? (
          <Button variant="ghost" size="sm" disabled={cancel.isPending} onClick={() => cancel.mutate()}>
            {cancel.isPending ? '正在取消…' : '取消生成'}
          </Button>
        ) : (
          <>
            {(deck?.status === 'partial' || failed > 0) && (
              <Button
                variant="ghost"
                size="sm"
                disabled={generate.isPending}
                onClick={() => generate.mutate({ regenerateAll: false })}
              >
                <RefreshCw className={cn('size-3.5', generate.isPending && 'animate-spin')} />
                继续生成
              </Button>
            )}
            <Button
              variant="ghost"
              size="sm"
              disabled={!slides.some((slide) => slide.status === 'ready')}
              onClick={() => setPresenting(true)}
            >
              <Play className="size-3.5" />
              演示
            </Button>
            <Button size="sm" disabled={slides.length === 0} onClick={() => setExporting(true)}>
              <Download className="size-4" />
              导出
            </Button>
            {slides.length > 0 && (
              <OverflowMenu
                disabled={generate.isPending}
                onRegenerateAll={() => generate.mutate({ regenerateAll: true })}
              />
            )}
          </>
        )}
      </WorkbenchHeader>

      {actionError && (
        <p role="alert" className="bg-negative/8 px-5 py-2 text-[13px] text-negative">
          {errorMessage(actionError)}
        </p>
      )}

      <div className="flex min-h-0 flex-1">
        {slides.length > 0 && (
          <Filmstrip
            projectId={project.id}
            slides={slides}
            theme={theme}
            activeId={activeId}
            locked={generating}
            onSelect={focusSlide}
            onReorder={reorder.mutate}
          />
        )}

        {slides.length === 0 ? (
          <EmptyStage
            pending={generate.isPending || deckQuery.isPending}
            onGenerate={() => generate.mutate({ regenerateAll: false })}
          />
        ) : (
          <SlideStage
            projectId={project.id}
            slides={slides}
            activeId={activeId}
            scrollRequest={scrollRequest}
            theme={theme}
            locked={generating}
            zoom={ZOOM_STEPS[zoomIndex]}
            canZoomOut={zoomIndex > 0}
            canZoomIn={zoomIndex < ZOOM_STEPS.length - 1}
            selection={selection}
            onSelectionChange={setSelection}
            onActiveChange={setActiveId}
            onOpenRelayout={() => {
              setRelayoutOpen(true)
              setRail(null)
            }}
            onZoom={(delta) =>
              setZoomIndex((current) =>
                Math.min(Math.max(current + delta, 0), ZOOM_STEPS.length - 1),
              )
            }
          />
        )}

        {active && relayoutOpen && active.layout_mode === 'flex' && (
          <RelayoutDock
            projectId={project.id}
            slide={active}
            theme={theme}
            open={relayoutOpen}
            disabled={generating || active.status !== 'ready'}
            onClose={() => setRelayoutOpen(false)}
          />
        )}

        {active && (
          <Rail
            project={project}
            slide={active}
            theme={theme}
            tab={rail}
            locked={generating}
            selectedBlockId={
              selection?.slideId === active.id ? selection.blockId : null
            }
            onTab={(next) => {
              setRelayoutOpen(false)
              setRail((current) => (current === next ? null : next))
            }}
            onOpenRelayout={() => {
              setRelayoutOpen(true)
              setRail(null)
            }}
          />
        )}
      </div>

      {presenting && (
        <PresentMode
          slides={slides.filter((slide) => slide.status === 'ready')}
          theme={theme}
          startIndex={Math.max(
            0,
            slides.filter((slide) => slide.status === 'ready').findIndex((slide) => slide.id === activeId),
          )}
          onClose={() => setPresenting(false)}
        />
      )}

      {exporting && deck && (
        <ExportDialog
          projectId={project.id}
          deck={deck}
          onClose={() => setExporting(false)}
          onLocate={focusSlide}
        />
      )}
    </div>
  )
}

function SlideStage({
  projectId,
  slides,
  activeId,
  scrollRequest,
  theme,
  locked,
  zoom,
  canZoomIn,
  canZoomOut,
  selection,
  onSelectionChange,
  onActiveChange,
  onOpenRelayout,
  onZoom,
}: {
  projectId: string
  slides: DeckSlide[]
  activeId: string | null
  scrollRequest: { id: string; nonce: number } | null
  theme: Theme
  locked: boolean
  zoom: number
  canZoomIn: boolean
  canZoomOut: boolean
  selection: BlockSelection | null
  onSelectionChange: (selection: BlockSelection | null) => void
  onActiveChange: (slideId: string) => void
  onOpenRelayout: () => void
  onZoom: (delta: 1 | -1) => void
}) {
  const scrollerRef = useRef<HTMLDivElement>(null)
  const slideElsRef = useRef(new Map<string, HTMLElement>())
  const ignoreObserverRef = useRef(false)
  const slideIdsKey = slides.map((slide) => slide.id).join('|')
  const active = slides.find((slide) => slide.id === activeId) ?? null
  const warnings =
    active?.issues.filter((issue) => issue.severity === 'warning') ?? []

  const bindSlideEl = (slideId: string, node: HTMLElement | null) => {
    if (node) slideElsRef.current.set(slideId, node)
    else slideElsRef.current.delete(slideId)
  }

  // 胶片条 / 导出定位：滚到目标页；滚动过程中忽略 observer，避免中间页抢焦点
  useEffect(() => {
    if (!scrollRequest) return
    const node = slideElsRef.current.get(scrollRequest.id)
    if (!node) return
    ignoreObserverRef.current = true
    node.scrollIntoView({ behavior: 'smooth', block: 'center' })
    const timer = window.setTimeout(() => {
      ignoreObserverRef.current = false
    }, 450)
    return () => window.clearTimeout(timer)
  }, [scrollRequest])

  useEffect(() => {
    const root = scrollerRef.current
    if (!root) return

    const ratios = new Map<string, number>()
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          const id = (entry.target as HTMLElement).dataset.slideId
          if (!id) continue
          if (entry.isIntersecting) ratios.set(id, entry.intersectionRatio)
          else ratios.delete(id)
        }
        if (ignoreObserverRef.current || ratios.size === 0) return
        let bestId: string | null = null
        let bestRatio = 0
        for (const [id, ratio] of ratios) {
          if (ratio > bestRatio) {
            bestRatio = ratio
            bestId = id
          }
        }
        if (bestId) onActiveChange(bestId)
      },
      { root, threshold: [0.25, 0.45, 0.65, 0.85], rootMargin: '-12% 0px -12% 0px' },
    )

    const nodes = Array.from(root.querySelectorAll<HTMLElement>('[data-slide-id]'))
    for (const node of nodes) {
      slideElsRef.current.set(node.dataset.slideId!, node)
      observer.observe(node)
    }
    return () => observer.disconnect()
  }, [slideIdsKey, onActiveChange])

  return (
    <main className="bg-stage flex min-w-0 flex-1 flex-col">
      <div ref={scrollerRef} className="scrollbar-slim flex-1 overflow-y-auto">
        <div className="mx-auto flex w-full max-w-[96rem] flex-col items-center gap-10 px-8 py-8">
          {slides.map((slide, index) => (
            <SlidePage
              key={slide.id}
              projectId={projectId}
              slide={slide}
              theme={theme}
              locked={locked}
              zoom={zoom}
              index={index}
              total={slides.length}
              active={slide.id === activeId}
              selectedBlockId={
                selection?.slideId === slide.id ? selection.blockId : null
              }
              onSelectBlock={(blockId) =>
                onSelectionChange(blockId ? { slideId: slide.id, blockId } : null)
              }
              onOpenRelayout={onOpenRelayout}
              bindEl={bindSlideEl}
            />
          ))}
        </div>
      </div>

      <footer className="flex flex-wrap items-center gap-4 border-t border-line bg-surface/70 px-4 py-2 backdrop-blur">
        <div className="flex items-center gap-1">
          <button
            type="button"
            aria-label="缩小"
            disabled={!canZoomOut}
            onClick={() => onZoom(-1)}
            className="grid size-7 place-items-center rounded-md text-ink-muted transition-colors hover:bg-surface-soft hover:text-ink disabled:opacity-30"
          >
            <Minus className="size-3.5" />
          </button>
          <span className="w-10 text-center text-xs text-ink-muted tabular-nums">
            {Math.round(zoom * 100)}%
          </span>
          <button
            type="button"
            aria-label="放大"
            disabled={!canZoomIn}
            onClick={() => onZoom(1)}
            className="grid size-7 place-items-center rounded-md text-ink-muted transition-colors hover:bg-surface-soft hover:text-ink disabled:opacity-30"
          >
            <Plus className="size-3.5" />
          </button>
        </div>

        <span className="text-xs text-ink-muted">
          {locked
            ? '生成中暂不可编辑'
            : active?.status === 'ready'
              ? '点击元素调样式；Ctrl/⌘+Z 撤销，Ctrl/⌘+Shift+Z 重做'
              : '向下滚动查看其他页面'}
        </span>

        {warnings.length > 0 && (
          <span className="flex items-center gap-1.5 text-xs text-warning">
            <AlertTriangle className="size-3.5" />
            {warnings.length} 处内容偏长
          </span>
        )}
      </footer>
    </main>
  )
}

function SlidePage({
  projectId,
  slide,
  theme,
  locked,
  zoom,
  index,
  total,
  active,
  selectedBlockId,
  onSelectBlock,
  onOpenRelayout,
  bindEl,
}: {
  projectId: string
  slide: DeckSlide
  theme: Theme
  locked: boolean
  zoom: number
  index: number
  total: number
  active: boolean
  selectedBlockId: string | null
  onSelectBlock: (blockId: string | null) => void
  onOpenRelayout: () => void
  bindEl: (slideId: string, node: HTMLElement | null) => void
}) {
  const {
    commit,
    commitStyle,
    commitFlex,
    commitCreateBlock,
    commitDeleteBlock,
    commitMutate,
    undo,
    redo,
    canUndo,
    canRedo,
    historyTick,
    status,
    error,
    refresh,
  } = useSlideSaveQueue(projectId, slide.id)
  const retry = useRetrySlide(projectId)
  const editable = slide.status === 'ready' && !locked && status !== 'conflict'
  const isFlex = slide.layout_mode === 'flex' && slide.layout_tree != null

  useEffect(() => {
    return registerSlideSaveHandlers(slide.id, {
      commitFlex,
      commitCreateBlock,
      commitDeleteBlock,
      commitMutate,
      undo,
    })
  }, [
    slide.id,
    commitFlex,
    commitCreateBlock,
    commitDeleteBlock,
    commitMutate,
    undo,
  ])
  const articleRef = useRef<HTMLElement | null>(null)
  const [blockEl, setBlockEl] = useState<HTMLElement | null>(null)
  const [flexPreview, setFlexPreview] = useState<FlexContainer | null>(null)
  const [flexDragging, setFlexDragging] = useState(false)
  const selectedBlock =
    selectedBlockId != null
      ? (slide.blocks.find((block) => block.id === selectedBlockId) ?? null)
      : null
  const renderSlide: Slide = flexPreview
    ? ({ ...toRenderSlide(slide), layout_tree: flexPreview } as Slide)
    : toRenderSlide(slide)
  const overflowSlotIds = new Set(
    slide.issues
      .filter(
        (issue) =>
          issue.code === 'overflow' ||
          issue.message.includes('溢出') ||
          issue.message.includes('超出画布'),
      )
      .flatMap((issue) => (issue.slot_id ? [issue.slot_id] : ['*'])),
  )

  useEffect(() => {
    setFlexPreview(null)
  }, [slide.id, slide.revision])

  useEffect(() => {
    if (!selectedBlockId || !articleRef.current) {
      setBlockEl(null)
      return
    }
    const node = articleRef.current.querySelector<HTMLElement>(
      `[data-block-id="${CSS.escape(selectedBlockId)}"]`,
    )
    setBlockEl(node)
  }, [selectedBlockId, slide.blocks, zoom, flexPreview])

  // 仅当前可视页响应撤销/重做，避免多页 SlidePage 抢同一快捷键
  useEffect(() => {
    if (!active || !editable) return

    const onKeyDown = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null
      const editingText =
        target?.isContentEditable ||
        target?.closest('[contenteditable="true"]') != null ||
        target?.tagName === 'INPUT' ||
        target?.tagName === 'TEXTAREA'

      if (
        isFlex &&
        selectedBlockId &&
        !editingText &&
        (event.key === 'Delete' || event.key === 'Backspace') &&
        !event.metaKey &&
        !event.ctrlKey &&
        !event.altKey
      ) {
        event.preventDefault()
        commitDeleteBlock(selectedBlockId)
        onSelectBlock(null)
        return
      }

      const mod = event.metaKey || event.ctrlKey
      if (!mod) return
      const key = event.key.toLowerCase()
      const isUndo = key === 'z' && !event.shiftKey
      const isRedo = (key === 'z' && event.shiftKey) || key === 'y'
      if (!isUndo && !isRedo) return

      // 系统输入框（若有）不拦截；画布 contenteditable 的未提交草稿由 EditableText 处理
      if (
        target &&
        (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA') &&
        !target.closest('[data-slide-id]')
      ) {
        return
      }

      if (isUndo) {
        if (!canUndo) return
        event.preventDefault()
        undo()
        return
      }
      if (!canRedo) return
      event.preventDefault()
      redo()
    }

    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [
    active,
    editable,
    canUndo,
    canRedo,
    undo,
    redo,
    historyTick,
    isFlex,
    selectedBlockId,
    commitDeleteBlock,
    onSelectBlock,
  ])

  return (
    <article
      ref={(node) => {
        articleRef.current = node
        bindEl(slide.id, node)
      }}
      data-slide-id={slide.id}
      aria-current={active ? 'true' : undefined}
      className="relative flex w-full flex-col items-center gap-2"
    >
      <div className="flex w-full max-w-[76rem] items-center gap-2 px-1">
        <span
          className={cn(
            'text-[11px] font-medium tabular-nums',
            active ? 'text-accent' : 'text-ink-muted',
          )}
        >
          {index + 1} / {total}
        </span>
        <span className="truncate text-[11px] text-ink-muted">{slide.title}</span>
        <SaveIndicator status={status} error={error} onRefresh={refresh} />
        {active && isFlex && editable && (
          <button
            type="button"
            onClick={onOpenRelayout}
            className="ml-auto inline-flex items-center gap-1 rounded-lg px-2 py-1 text-[11px] font-medium text-ink-soft transition-colors hover:bg-surface-soft hover:text-ink"
          >
            <RefreshCw className="size-3" />
            换排布
          </button>
        )}
      </div>

      {slide.status === 'ready' ? (
        <div
          style={{ width: `${zoom * 100}%`, maxWidth: zoom <= 1 ? '76rem' : 'none' }}
          className={cn(
            'relative shrink-0 shadow-slide transition-[box-shadow,outline-color]',
            active ? 'outline-2 outline-accent/35 outline-offset-4' : 'outline-none',
          )}
        >
          <div className={cn('relative', editable ? 'overflow-visible' : 'overflow-hidden')}>
            <SlideView
              slide={renderSlide}
              theme={theme}
              slideIndex={index}
              editable={editable}
              selectedBlockId={selectedBlockId}
              onSelectBlock={onSelectBlock}
              onCommit={commit}
              overflowMode={editable ? 'reveal' : 'clip'}
              overflowSlotIds={overflowSlotIds}
            />
            {isFlex && editable && (
              <FlexEditLayer
                projectId={projectId}
                slide={slide}
                tree={slide.layout_tree as FlexContainer}
                selectedBlockId={selectedBlockId}
                busy={status === 'saving'}
                onPreviewTree={setFlexPreview}
                onCommitTree={commitFlex}
                onSelectBlock={(blockId) => onSelectBlock(blockId)}
                onDraggingChange={setFlexDragging}
              />
            )}
          </div>
        </div>
      ) : (
        <div
          style={{ width: `${zoom * 100}%`, maxWidth: zoom <= 1 ? '76rem' : 'none' }}
          className="grid min-h-56 place-items-center"
        >
          <PendingStage
            slide={slide}
            disabled={locked || retry.isPending}
            onRetry={() => retry.mutate(slide.id)}
          />
        </div>
      )}

      {editable &&
        selectedBlock &&
        selectedBlock.type !== 'chart' &&
        !flexDragging && (
        <ElementToolbar
          articleEl={articleRef.current}
          blockEl={blockEl}
          block={selectedBlock}
          theme={theme}
          disabled={status === 'saving'}
          onChange={(style: BlockStyle | null) => commitStyle(selectedBlock.id, style)}
          onCommitContent={(change) => commit(selectedBlock.id, change)}
          flexPreset={
            isFlex && slide.layout_tree != null
              ? (findLeafParent(slide.layout_tree as FlexContainer, selectedBlock.id)
                  ?.parent.preset ?? null)
              : null
          }
          onFlexPresetChange={
            isFlex && slide.layout_tree != null
              ? (preset) => {
                  const tree = slide.layout_tree as FlexContainer
                  const found = findLeafParent(tree, selectedBlock.id)
                  if (!found) return
                  const next = setContainerPreset(tree, found.parent.id, preset)
                  if (!next) return
                  commitFlex(next)
                }
              : undefined
          }
          onDelete={
            isFlex
              ? () => {
                  commitDeleteBlock(selectedBlock.id)
                  onSelectBlock(null)
                }
              : undefined
          }
          onDismiss={() => onSelectBlock(null)}
        />
      )}
      {editable &&
        selectedBlock?.type === 'chart' &&
        !flexDragging && (
          <ChartDataEditor
            articleEl={articleRef.current}
            blockEl={blockEl}
            block={selectedBlock}
            disabled={status === 'saving'}
            onCommit={(change) => commit(selectedBlock.id, change)}
            onDismiss={() => onSelectBlock(null)}
          />
        )}
    </article>
  )
}

function PendingStage({
  slide,
  disabled,
  onRetry,
}: {
  slide: DeckSlide
  disabled: boolean
  onRetry: () => void
}) {
  if (slide.status === 'failed') {
    return (
      <div className="max-w-sm rounded-3xl border border-line bg-surface px-8 py-10 text-center shadow-card">
        <AlertTriangle className="mx-auto mb-3 size-5 text-negative" />
        <p className="text-sm font-medium">这一页没有生成成功</p>
        <p className="mt-1.5 text-[13px] leading-relaxed text-ink-muted">
          {slide.error ?? '可以直接重试，其他页面不受影响。'}
        </p>
        <Button className="mt-5" size="sm" disabled={disabled} onClick={onRetry}>
          <RotateCw className="size-3.5" />
          重试这一页
        </Button>
      </div>
    )
  }

  return (
    <div className="flex flex-col items-center gap-3 text-ink-muted">
      <Loader2 className="size-5 animate-spin" />
      <p className="text-[13px]">正在生成这一页…</p>
    </div>
  )
}

function EmptyStage({ pending, onGenerate }: { pending: boolean; onGenerate: () => void }) {
  return (
    <main className="bg-stage grid flex-1 place-items-center p-8">
      <div className="max-w-sm rounded-3xl border border-line bg-surface px-8 py-10 text-center shadow-card">
        <Sparkles className="mx-auto mb-3 size-5 text-accent" />
        <p className="text-sm font-medium">大纲已确认，还没有生成页面</p>
        <p className="mt-1.5 text-[13px] leading-relaxed text-ink-muted">
          生成过程中就能编辑，完成一页显示一页。
        </p>
        <Button className="mt-5" disabled={pending} onClick={onGenerate}>
          {pending ? <Loader2 className="size-4 animate-spin" /> : <Sparkles className="size-4" />}
          生成 PPT
        </Button>
      </div>
    </main>
  )
}

function Rail({
  project,
  slide,
  theme,
  tab,
  locked,
  selectedBlockId,
  onTab,
  onOpenRelayout,
}: {
  project: ProjectDetail
  slide: DeckSlide
  theme: Theme
  tab: RailTab | null
  locked: boolean
  selectedBlockId: string | null
  onTab: (tab: RailTab) => void
  onOpenRelayout: () => void
}) {
  const panelOpen = Boolean(tab)

  return (
    <div className="flex shrink-0">
      {panelOpen && (
        <aside className="scrollbar-slim w-80 overflow-y-auto border-l border-line bg-surface px-4 py-4">
          {tab === 'ai' && <AiEditPanel projectId={project.id} slide={slide} />}
          {tab === 'theme' && <ThemePanel project={project} disabled={locked} />}
          {tab === 'layout' && (
            <LayoutPanel
              projectId={project.id}
              slide={slide}
              theme={theme}
              selectedBlockId={selectedBlockId}
              disabled={locked}
              onOpenRelayout={onOpenRelayout}
            />
          )}
          {tab === 'image' && (
            <ImagePanel projectId={project.id} slide={slide} disabled={locked} />
          )}
        </aside>
      )}

      <div className="flex w-13 flex-col items-center gap-1.5 border-l border-line bg-surface py-3">
        {RAIL_TABS.map(({ tab: value, label, icon: Icon }) => (
          <button
            key={value}
            type="button"
            title={label}
            aria-label={label}
            aria-pressed={tab === value}
            onClick={() => onTab(value)}
            className={cn(
              'grid size-9 place-items-center rounded-xl transition-colors',
              tab === value
                ? 'bg-accent-soft text-accent'
                : 'text-ink-muted hover:bg-surface-soft hover:text-ink',
            )}
          >
            <Icon className="size-4.5" />
          </button>
        ))}
      </div>
    </div>
  )
}

function OverflowMenu({
  disabled,
  onRegenerateAll,
}: {
  disabled?: boolean
  onRegenerateAll: () => void
}) {
  const [open, setOpen] = useState(false)
  const rootRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const onPointer = (event: MouseEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', onPointer)
    return () => document.removeEventListener('mousedown', onPointer)
  }, [open])

  return (
    <div ref={rootRef} className="relative">
      <button
        type="button"
        aria-label="更多操作"
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
        className="grid size-8 place-items-center rounded-lg text-ink-muted transition-colors hover:bg-surface-soft hover:text-ink"
      >
        <MoreHorizontal className="size-4" />
      </button>

      {open && (
        <div
          role="menu"
          className="absolute top-full right-0 z-40 mt-2 w-52 overflow-hidden rounded-2xl border border-line bg-surface shadow-pop"
        >
          <button
            type="button"
            role="menuitem"
            disabled={disabled}
            onClick={() => {
              setOpen(false)
              onRegenerateAll()
            }}
            className="w-full px-4 py-3 text-left text-[13px] text-ink-soft transition-colors hover:bg-surface-soft hover:text-ink disabled:opacity-50"
          >
            全部重新生成
            <span className="mt-0.5 block text-xs text-ink-muted">会覆盖所有页面的现有内容</span>
          </button>
        </div>
      )}
    </div>
  )
}

function SaveIndicator({
  status,
  error,
  onRefresh,
}: {
  status: SaveStatus
  error: string | null
  onRefresh: () => void
}) {
  if (status === 'idle') return null

  if (status === 'saving') {
    return <span className="ml-auto text-xs text-ink-muted">保存中…</span>
  }
  if (status === 'saved') {
    return <span className="ml-auto text-xs text-positive">已保存</span>
  }
  if (status === 'conflict') {
    return (
      <span className="ml-auto flex items-center gap-2 text-xs text-negative">
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
    <span role="alert" className="ml-auto text-xs text-negative">
      {error ?? '保存失败'}
    </span>
  )
}
