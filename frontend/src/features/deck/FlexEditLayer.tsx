import { GripVertical, Plus } from 'lucide-react'
import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type PointerEvent as ReactPointerEvent,
} from 'react'
import { InsertMenu, type InsertAnchor } from '@/features/deck/BlockInsertRail'
import {
  collectColumnDividers,
  collectInsertSlots,
  collectRowDividers,
  ensureResizePair,
  findContainerById,
  growsFromDividerDrag,
  iterLeaves,
  moveLeaf,
  ratiosFromDividerDrag,
  resolveDropTarget,
  slotsNearBlock,
  updateChildGrows,
  updateRowRatios,
  type ColumnDivider,
  type DropTarget,
  type InsertSlot,
  type RowDivider,
} from '@/features/deck/flexTree'
import type { DeckSlide } from '@/features/deck/types'
import { cn } from '@/lib/utils'
import { solve, solveNodeAreas, type FlexContainer, type FlexNode } from '@/render/flexLayout'

type DragSession =
  | {
      kind: 'reorder'
      blockId: string
      drop: DropTarget | null
      grabOffsetX: number
      grabOffsetY: number
      ghostW: number
      ghostH: number
      pointerX: number
      pointerY: number
    }
  | {
      kind: 'ratio'
      rowId: string
      leftIndex: number
      rowX: number
      rowW: number
      baseTree: FlexContainer
    }
  | {
      kind: 'grow'
      columnId: string
      topIndex: number
      colY: number
      colH: number
      baseTree: FlexContainer
    }

const BLOCK_LABEL: Record<string, string> = {
  text: '文本',
  bullets: '列表',
  image: '图片',
  kpi: 'KPI',
  table: '表格',
  chart: '图表',
}

/**
 * flex 编辑叠加层：少而准的 +、跟手拖拽、行列拉伸。
 */
export function FlexEditLayer({
  projectId,
  slide,
  tree,
  selectedBlockId,
  disabled,
  onPreviewTree,
  onCommitTree,
  onSelectBlock,
  onDraggingChange,
}: {
  projectId: string
  slide: DeckSlide
  tree: FlexContainer
  selectedBlockId: string | null
  disabled?: boolean
  onPreviewTree?: (next: FlexContainer | null) => void
  onCommitTree: (next: FlexContainer) => void
  onSelectBlock?: (blockId: string) => void
  onDraggingChange?: (dragging: boolean) => void
}) {
  const rootRef = useRef<HTMLDivElement>(null)
  const treeRef = useRef(tree)
  treeRef.current = tree
  const onCommitRef = useRef(onCommitTree)
  onCommitRef.current = onCommitTree
  const onPreviewRef = useRef(onPreviewTree)
  onPreviewRef.current = onPreviewTree
  const onDraggingRef = useRef(onDraggingChange)
  onDraggingRef.current = onDraggingChange

  const [drag, setDrag] = useState<DragSession | null>(null)
  const [previewTree, setPreviewTree] = useState<FlexContainer | null>(null)
  const [hoveredBlockId, setHoveredBlockId] = useState<string | null>(null)
  const [hoveredDividerKey, setHoveredDividerKey] = useState<string | null>(null)
  const [insertMenu, setInsertMenu] = useState<(InsertAnchor & { x: number; y: number }) | null>(
    null,
  )
  const [hoveredSlotKey, setHoveredSlotKey] = useState<string | null>(null)

  const dragRef = useRef<DragSession | null>(null)
  dragRef.current = drag
  const previewRef = useRef<FlexContainer | null>(null)
  previewRef.current = previewTree

  const activeTree = previewTree ?? tree
  const placements = useMemo(() => {
    const map = new Map<string, { x: number; y: number; w: number; h: number }>()
    for (const placed of solve(activeTree)) {
      map.set(placed.block_id, placed.rect)
    }
    return map
  }, [activeTree])

  const basePlacements = useMemo(() => {
    const map = new Map<string, { x: number; y: number; w: number; h: number }>()
    for (const placed of solve(tree)) {
      map.set(placed.block_id, placed.rect)
    }
    return map
  }, [tree])
  const basePlacementsRef = useRef(basePlacements)
  basePlacementsRef.current = basePlacements

  const rowDividers = useMemo(
    () => collectRowDividers(activeTree, placements),
    [activeTree, placements],
  )
  const columnDividers = useMemo(
    () => collectColumnDividers(activeTree, placements),
    [activeTree, placements],
  )

  const focusBlockId = hoveredBlockId ?? selectedBlockId
  const insertSlots = useMemo(() => {
    if (drag) return []
    const all = collectInsertSlots(tree, basePlacements)
    return slotsNearBlock(all, tree, focusBlockId)
  }, [tree, basePlacements, drag, focusBlockId])

  const blockIds = useMemo(
    () => iterLeaves(tree).map((leaf) => leaf.block_id),
    [tree],
  )

  const dragging = drag != null
  const draggingBlockId = drag?.kind === 'reorder' ? drag.blockId : null

  useEffect(() => {
    onDraggingRef.current?.(dragging)
  }, [dragging])

  useEffect(() => {
    if (!draggingBlockId) return
    const host = rootRef.current?.parentElement
    if (!host) return
    const el = host.querySelector<HTMLElement>(
      `[data-block-id="${CSS.escape(draggingBlockId)}"]`,
    )
    if (!el) return
    const prev = el.style.opacity
    el.style.opacity = '0.15'
    return () => {
      el.style.opacity = prev
    }
  }, [draggingBlockId, previewTree])

  useEffect(() => {
    if (!dragging) return

    const toNorm = (clientX: number, clientY: number) => {
      const el = rootRef.current
      if (!el) return null
      const box = el.getBoundingClientRect()
      if (box.width <= 0 || box.height <= 0) return null
      return {
        x: (clientX - box.left) / box.width,
        y: (clientY - box.top) / box.height,
      }
    }

    const onMove = (event: PointerEvent) => {
      const session = dragRef.current
      if (!session) return
      const pointer = toNorm(event.clientX, event.clientY)
      if (!pointer) return
      const currentTree = treeRef.current

      if (session.kind === 'reorder') {
        // 拖动中不重排预览，避免其它块尺寸跟着跳；仅更新幽灵与落点线
        const drop = resolveDropTarget({
          root: currentTree,
          placements: basePlacementsRef.current,
          pointer,
          draggedBlockId: session.blockId,
        })
        setDrag({
          ...session,
          drop,
          pointerX: pointer.x,
          pointerY: pointer.y,
        })
        return
      }

      if (session.kind === 'ratio') {
        const t = (pointer.x - session.rowX) / Math.max(session.rowW, 1e-9)
        const row = findContainerById(session.baseTree, session.rowId)
        if (!row || row.type !== 'row') return
        const base =
          row.ratios?.length === row.children.length
            ? [...row.ratios]
            : Array.from({ length: row.children.length }, () => 100 / row.children.length)
        const nextRatios = ratiosFromDividerDrag({
          ratios: base,
          leftIndex: session.leftIndex,
          t,
        })
        const next = updateRowRatios(session.baseTree, session.rowId, nextRatios)
        if (next) {
          setPreviewTree(next)
          onPreviewRef.current?.(next)
        }
        return
      }

      const t = (pointer.y - session.colY) / Math.max(session.colH, 1e-9)
      const column = findContainerById(session.baseTree, session.columnId)
      if (!column || column.type !== 'column') return
      const base = column.children.map((child) => child.grow ?? 1)
      const nextGrows = growsFromDividerDrag({
        grows: base,
        topIndex: session.topIndex,
        t,
      })
      const next = updateChildGrows(session.baseTree, session.columnId, nextGrows)
      if (next) {
        setPreviewTree(next)
        onPreviewRef.current?.(next)
      }
    }

    const onUp = () => {
      const session = dragRef.current
      const draft = previewRef.current
      setDrag(null)
      setPreviewTree(null)
      onPreviewRef.current?.(null)
      if (!session) return
      if (session.kind === 'reorder') {
        if (!session.drop) return
        const next = moveLeaf(
          treeRef.current,
          session.blockId,
          session.drop.parentId,
          session.drop.index,
        )
        if (next) onCommitRef.current(next)
        return
      }
      if (draft) onCommitRef.current(draft)
    }

    window.addEventListener('pointermove', onMove)
    window.addEventListener('pointerup', onUp)
    window.addEventListener('pointercancel', onUp)
    return () => {
      window.removeEventListener('pointermove', onMove)
      window.removeEventListener('pointerup', onUp)
      window.removeEventListener('pointercancel', onUp)
    }
  }, [dragging])

  useEffect(() => {
    const el = rootRef.current
    if (!el || disabled) return
    const parent = el.parentElement
    if (!parent) return

    const toNorm = (clientX: number, clientY: number) => {
      const box = el.getBoundingClientRect()
      if (box.width <= 0 || box.height <= 0) return null
      return {
        x: (clientX - box.left) / box.width,
        y: (clientY - box.top) / box.height,
      }
    }

    const onMove = (event: PointerEvent) => {
      if (dragRef.current) return
      const pointer = toNorm(event.clientX, event.clientY)
      if (!pointer) return
      let hit: string | null = null
      for (const [blockId, rect] of basePlacementsRef.current) {
        if (
          pointer.x >= rect.x &&
          pointer.x <= rect.x + rect.w &&
          pointer.y >= rect.y &&
          pointer.y <= rect.y + rect.h
        ) {
          hit = blockId
          break
        }
      }
      setHoveredBlockId(hit)
    }
    const onLeave = () => {
      if (!dragRef.current) setHoveredBlockId(null)
    }

    parent.addEventListener('pointermove', onMove)
    parent.addEventListener('pointerleave', onLeave)
    return () => {
      parent.removeEventListener('pointermove', onMove)
      parent.removeEventListener('pointerleave', onLeave)
    }
  }, [disabled])

  const startReorder = (blockId: string, event: ReactPointerEvent) => {
    if (disabled) return
    event.preventDefault()
    event.stopPropagation()
    setInsertMenu(null)
    onSelectBlock?.(blockId)

    const rect = basePlacements.get(blockId)
    const el = rootRef.current
    if (!rect || !el) {
      setDrag({
        kind: 'reorder',
        blockId,
        drop: null,
        grabOffsetX: 0.02,
        grabOffsetY: 0.02,
        ghostW: 0.2,
        ghostH: 0.12,
        pointerX: rect?.x ?? 0,
        pointerY: rect?.y ?? 0,
      })
      return
    }
    const box = el.getBoundingClientRect()
    const pointerX = (event.clientX - box.left) / box.width
    const pointerY = (event.clientY - box.top) / box.height
    setDrag({
      kind: 'reorder',
      blockId,
      drop: null,
      grabOffsetX: pointerX - rect.x,
      grabOffsetY: pointerY - rect.y,
      ghostW: rect.w,
      ghostH: rect.h,
      pointerX,
      pointerY,
    })
  }

  const measureRowSpan = (baseTree: FlexContainer, rowId: string) => {
    const row = findContainerById(baseTree, rowId)
    if (!row || row.type !== 'row') return null
    const areas = solveNodeAreas(baseTree)
    const rowArea = areas.get(rowId)
    if (rowArea && rowArea.w > 0) {
      return { rowX: rowArea.x, rowW: rowArea.w }
    }
    let x0 = Infinity
    let x1 = -Infinity
    for (const child of row.children) {
      for (const leaf of iterLeaves(child as FlexNode)) {
        const rect = solve(baseTree).find((p) => p.block_id === leaf.block_id)?.rect
        if (!rect) continue
        x0 = Math.min(x0, rect.x)
        x1 = Math.max(x1, rect.x + rect.w)
      }
    }
    if (!Number.isFinite(x0) || !Number.isFinite(x1) || x1 <= x0) return null
    return { rowX: x0, rowW: x1 - x0 }
  }

  const measureColSpan = (baseTree: FlexContainer, columnId: string) => {
    const areas = solveNodeAreas(baseTree)
    const colArea = areas.get(columnId)
    if (colArea && colArea.h > 0) {
      return { colY: colArea.y, colH: colArea.h }
    }
    return null
  }

  const startRatio = (
    divider: RowDivider,
    event: ReactPointerEvent,
    baseTree: FlexContainer = tree,
  ) => {
    if (disabled) return
    event.preventDefault()
    event.stopPropagation()
    setInsertMenu(null)

    const span = measureRowSpan(baseTree, divider.rowId)
    if (!span) return

    setPreviewTree(baseTree)
    onPreviewTree?.(baseTree)
    setDrag({
      kind: 'ratio',
      rowId: divider.rowId,
      leftIndex: divider.leftIndex,
      rowX: span.rowX,
      rowW: span.rowW,
      baseTree,
    })
  }

  const startGrow = (
    divider: ColumnDivider,
    event: ReactPointerEvent,
    baseTree: FlexContainer = tree,
  ) => {
    if (disabled) return
    event.preventDefault()
    event.stopPropagation()
    setInsertMenu(null)

    const span = measureColSpan(baseTree, divider.columnId)
    if (!span) return

    setPreviewTree(baseTree)
    onPreviewTree?.(baseTree)
    setDrag({
      kind: 'grow',
      columnId: divider.columnId,
      topIndex: divider.topIndex,
      colY: span.colY,
      colH: span.colH,
      baseTree,
    })
  }

  /** 选中块边手柄：先 ensure spacer/包装，再开拖 */
  const beginBlockResize = (
    blockId: string,
    axis: 'x' | 'y',
    event: ReactPointerEvent,
  ) => {
    if (disabled) return
    const ensured = ensureResizePair(tree, blockId, axis)
    if (!ensured) return
    if (axis === 'x') {
      startRatio(
        {
          rowId: ensured.containerId,
          leftIndex: ensured.index,
          x: 0,
          y: 0,
          h: 0,
        },
        event,
        ensured.tree,
      )
      return
    }
    startGrow(
      {
        columnId: ensured.containerId,
        topIndex: ensured.index,
        x: 0,
        y: 0,
        w: 0,
      },
      event,
      ensured.tree,
    )
  }

  const openInsert = (slot: InsertSlot, event: ReactPointerEvent) => {
    if (disabled) return
    event.preventDefault()
    event.stopPropagation()
    setInsertMenu({
      parentId: slot.parentId,
      index: slot.index,
      x: slot.x,
      y: slot.y,
    })
  }

  const visibleHandleId = draggingBlockId ?? selectedBlockId ?? hoveredBlockId

  const ghostLabel = (() => {
    if (!draggingBlockId) return ''
    const block = slide.blocks.find((item) => item.id === draggingBlockId)
    if (!block) return '内容块'
    if (block.type === 'text') {
      const text = block.text.trim()
      return text ? text.slice(0, 24) : '文本'
    }
    if (block.type === 'bullets') {
      return block.items[0]?.trim() || '列表'
    }
    if (block.type === 'kpi') return block.value || 'KPI'
    return BLOCK_LABEL[block.type] ?? '内容块'
  })()

  const selectedRect =
    selectedBlockId != null ? placements.get(selectedBlockId) : null

  return (
    <div ref={rootRef} className="pointer-events-none absolute inset-0 z-10">
      {rowDividers.map((divider) => {
        const key = `row:${divider.rowId}-${divider.leftIndex}`
        const active =
          (drag?.kind === 'ratio' &&
            drag.rowId === divider.rowId &&
            drag.leftIndex === divider.leftIndex) ||
          hoveredDividerKey === key
        return (
          <div
            key={key}
            role="separator"
            aria-orientation="vertical"
            title="拖动调整宽度"
            className="pointer-events-auto absolute z-20 flex w-3 -translate-x-1/2 cursor-col-resize justify-center"
            style={{
              left: `${divider.x * 100}%`,
              top: `${divider.y * 100}%`,
              height: `${divider.h * 100}%`,
            }}
            onPointerEnter={() => setHoveredDividerKey(key)}
            onPointerLeave={() =>
              setHoveredDividerKey((current) => (current === key ? null : current))
            }
            onPointerDown={(event) => startRatio(divider, event)}
          >
            <span
              className={cn(
                'h-full w-0.5 rounded-full transition-colors',
                active || hoveredDividerKey === key ? 'bg-accent/60' : 'bg-transparent',
              )}
            />
          </div>
        )
      })}

      {columnDividers.map((divider) => {
        const key = `col:${divider.columnId}-${divider.topIndex}`
        const active =
          (drag?.kind === 'grow' &&
            drag.columnId === divider.columnId &&
            drag.topIndex === divider.topIndex) ||
          hoveredDividerKey === key
        return (
          <div
            key={key}
            role="separator"
            aria-orientation="horizontal"
            title="拖动调整高度"
            className="pointer-events-auto absolute z-20 flex h-3 -translate-y-1/2 cursor-row-resize items-center"
            style={{
              left: `${divider.x * 100}%`,
              top: `${divider.y * 100}%`,
              width: `${divider.w * 100}%`,
            }}
            onPointerEnter={() => setHoveredDividerKey(key)}
            onPointerLeave={() =>
              setHoveredDividerKey((current) => (current === key ? null : current))
            }
            onPointerDown={(event) => startGrow(divider, event)}
          >
            <span
              className={cn(
                'w-full h-0.5 rounded-full transition-colors',
                active || hoveredDividerKey === key ? 'bg-accent/60' : 'bg-transparent',
              )}
            />
          </div>
        )
      })}

      {!disabled &&
        !dragging &&
        insertSlots.map((slot) => {
          const key = `${slot.parentId}:${slot.index}:${slot.axis}`
          const hot = hoveredSlotKey === key || insertMenu != null
          return (
            <button
              key={key}
              type="button"
              title="在此处插入"
              aria-label="在此处插入"
              className={cn(
                'pointer-events-auto absolute z-20 grid size-5 -translate-x-1/2 -translate-y-1/2 place-items-center',
                'rounded-full border border-line bg-surface text-ink-muted shadow-sm transition-opacity',
                hot ? 'opacity-100' : 'opacity-70',
                'hover:border-accent hover:text-accent hover:opacity-100',
              )}
              style={{
                left: `${slot.x * 100}%`,
                top: `${slot.y * 100}%`,
              }}
              onPointerEnter={() => setHoveredSlotKey(key)}
              onPointerLeave={() =>
                setHoveredSlotKey((current) => (current === key ? null : current))
              }
              onPointerDown={(event) => openInsert(slot, event)}
            >
              <Plus className="size-3" />
            </button>
          )
        })}

      {blockIds.map((blockId) => {
        if (draggingBlockId === blockId) return null
        const rect = placements.get(blockId)
        if (!rect) return null
        const show = !disabled && visibleHandleId === blockId
        if (!show) return null
        const isSelected = selectedBlockId === blockId
        return (
          <button
            key={blockId}
            type="button"
            title="拖动排序"
            aria-label="拖动排序"
            className={cn(
              'pointer-events-auto absolute z-20 grid size-5 place-items-center',
              'rounded-md border bg-surface text-ink-muted shadow-sm transition-opacity',
              'cursor-grab active:cursor-grabbing',
              isSelected
                ? 'border-accent/50 text-ink opacity-100'
                : 'border-line opacity-90 hover:opacity-100 hover:text-ink',
            )}
            style={{
              left: `calc(${rect.x * 100}% + 3px)`,
              top: `calc(${rect.y * 100}% + 3px)`,
            }}
            onPointerDown={(event) => startReorder(blockId, event)}
          >
            <GripVertical className="size-3" />
          </button>
        )
      })}

      {selectedBlockId && selectedRect && !disabled && !dragging && (
        <>
          <div
            role="separator"
            title="拖动调整高度"
            className="pointer-events-auto absolute z-30 flex h-3 -translate-y-1/2 cursor-row-resize items-center justify-center"
            style={{
              left: `${selectedRect.x * 100}%`,
              top: `${(selectedRect.y + selectedRect.h) * 100}%`,
              width: `${selectedRect.w * 100}%`,
            }}
            onPointerDown={(event) => beginBlockResize(selectedBlockId, 'y', event)}
          >
            <span className="h-1 w-9 rounded-full bg-accent/75 shadow-sm" />
          </div>
          <div
            role="separator"
            title="拖动调整宽度"
            className="pointer-events-auto absolute z-30 flex w-3 -translate-x-1/2 cursor-col-resize items-center justify-center"
            style={{
              left: `${(selectedRect.x + selectedRect.w) * 100}%`,
              top: `${selectedRect.y * 100}%`,
              height: `${selectedRect.h * 100}%`,
            }}
            onPointerDown={(event) => beginBlockResize(selectedBlockId, 'x', event)}
          >
            <span className="h-9 w-1 rounded-full bg-accent/75 shadow-sm" />
          </div>
        </>
      )}

      {drag?.kind === 'reorder' && (
        <div
          aria-hidden
          className="absolute z-40 overflow-hidden rounded-lg border border-accent/50 bg-surface/90 px-2 py-1.5 shadow-pop backdrop-blur-sm"
          style={{
            left: `${(drag.pointerX - drag.grabOffsetX) * 100}%`,
            top: `${(drag.pointerY - drag.grabOffsetY) * 100}%`,
            width: `${drag.ghostW * 100}%`,
            height: `${drag.ghostH * 100}%`,
            opacity: 0.92,
          }}
        >
          <div className="flex h-full items-start gap-1.5">
            <GripVertical className="mt-0.5 size-3 shrink-0 text-ink-muted" />
            <span className="line-clamp-3 text-[11px] leading-snug text-ink-soft">
              {ghostLabel}
            </span>
          </div>
        </div>
      )}

      {drag?.kind === 'reorder' && drag.drop && (
        <div
          aria-hidden
          className="absolute z-30 rounded-full bg-accent/80"
          style={
            drag.drop.line.axis === 'y'
              ? {
                  left: `${drag.drop.line.x * 100}%`,
                  top: `${drag.drop.line.y * 100}%`,
                  width: `${drag.drop.line.w * 100}%`,
                  height: 3,
                  transform: 'translateY(-1.5px)',
                }
              : {
                  left: `${drag.drop.line.x * 100}%`,
                  top: `${drag.drop.line.y * 100}%`,
                  width: 3,
                  height: `${drag.drop.line.h * 100}%`,
                  transform: 'translateX(-1.5px)',
                }
          }
        />
      )}

      {insertMenu && !disabled && (
        <div
          className="absolute z-30"
          style={{
            left: `min(${insertMenu.x * 100}%, calc(100% - 12rem))`,
            top: `min(${insertMenu.y * 100}%, calc(100% - 14rem))`,
          }}
        >
          <InsertMenu
            projectId={projectId}
            slide={slide}
            anchor={{ parentId: insertMenu.parentId, index: insertMenu.index }}
            disabled={disabled}
            onClose={() => setInsertMenu(null)}
          />
        </div>
      )}
    </div>
  )
}
