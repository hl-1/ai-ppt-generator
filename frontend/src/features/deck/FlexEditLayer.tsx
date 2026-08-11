import { GripVertical } from 'lucide-react'
import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
  type PointerEvent as ReactPointerEvent,
} from 'react'
import { insertColumnsAt } from '@/features/deck/BlockInsertRail'
import { normalizeGrows } from '@/features/deck/flexNormalize'
import {
  applyVerticalResizeDrag,
  collectColumnDividers,
  collectRowDividers,
  ensureResizePair,
  findContainerById,
  isSpacer,
  iterLeaves,
  leafOffset,
  moveLeaf,
  ratiosFromDividerDrag,
  resolveDropTarget,
  resolveInsertAnchor,
  setLeafOffset,
  updateRowRatios,
  type ColumnDivider,
  type DropTarget,
  type ResizePair,
  type ResizeSide,
  type RowDivider,
} from '@/features/deck/flexTree'
import {
  getSlideSaveHandlers,
  registerInsertDragStarter,
  type InsertDragPayload,
} from '@/features/deck/slideSaveBridge'
import type { DeckSlide } from '@/features/deck/types'
import { cn } from '@/lib/utils'
import { solve, solveNodeAreas, type FlexContainer, type FlexNode } from '@/render/flexLayout'
import { CANVAS_HEIGHT_PT, CANVAS_WIDTH_PT } from '@/render/types'

/** 横向拉伸所需的行内分隔线定位 */
type RatioAxis = {
  rowId: string
  leftIndex: number
  rowX: number
  rowW: number
}

/** 纵向拉伸所需的列内分隔线定位 */
type GrowAxis = {
  columnId: string
  topIndex: number
  colY: number
  colH: number
}

/** 块边缩放：pointerdown 可 ensure，但需越过阈值才 preview/commit */
type ResizeGate = {
  activated: boolean
  deferPreview: boolean
  startClientX: number
  startClientY: number
  /**
   * 四角双轴拖：越过激活阈值时按主方向锁定。
   * 上下为主则忽略横向，避免竖直拉缩时左右抖动改宽度。
   */
  axisLock?: 'x' | 'y' | 'both'
}

type RatioDragAxis = RatioAxis & { startT: number; originX: number }
type GrowDragAxis = GrowAxis & { startT: number; originY: number }

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
      kind: 'insert'
      payload: InsertDragPayload
      drop: DropTarget | null
      grabOffsetX: number
      grabOffsetY: number
      ghostW: number
      ghostH: number
      pointerX: number
      pointerY: number
      activated: boolean
      startClientX: number
      startClientY: number
    }
  | ({ kind: 'ratio'; baseTree: FlexContainer } & RatioDragAxis & ResizeGate)
  | ({
      kind: 'grow'
      baseTree: FlexContainer
      /** 角点按下时只 ensure 了 Y；激活后若主轴含 X 再补 ensure */
      pendingCorner?: {
        blockId: string
        sideX: ResizeSide
        originX: number
      }
    } & GrowDragAxis &
      ResizeGate)
  | {
      kind: 'box'
      baseTree: FlexContainer
      x: RatioDragAxis
      y: GrowDragAxis
    } & ResizeGate
  | {
      kind: 'offset'
      blockId: string
      baseTree: FlexContainer
      baseX: number
      baseY: number
      startX: number
      startY: number
    }

const BLOCK_LABEL: Record<string, string> = {
  text: '文本',
  bullets: '列表',
  image: '图片',
  kpi: 'KPI',
  cards: '卡片',
  callout: '提示',
  table: '表格',
  chart: '图表',
}

type RectLike = { x: number; y: number; w: number; h: number }

const pct = (value: number) => `${value * 100}%`

/**
 * 对角线判定：次轴 / 主轴 ≥ 该值才视为双轴，否则锁主轴。
 * 偏严，避免「上下拖时手抖左右」改宽度。
 */
const AXIS_DIAGONAL_MIN = 0.7
/** 角点激活：横向位移未达此像素前绝不 ensure X */
const AXIS_X_GATE_PX = 12
/** 窄于此时隐藏角点，只留边手柄，避免三列 KPI 误触双轴 */
const NARROW_BLOCK_HIDE_CORNER = 0.32

/**
 * 边手柄相对块尺寸让出四角。
 * 不用整页绝对 inset，否则三列 KPI 等窄块上下边命中会被吃光。
 */
export function edgeCornerInset(rect: RectLike): { x: number; y: number } {
  const minEdgeW = Math.max(rect.w * 0.4, Math.min(0.02, rect.w))
  const minEdgeH = Math.max(rect.h * 0.4, Math.min(0.02, rect.h))
  const maxInsetX = Math.max(0, (rect.w - minEdgeW) / 2)
  const maxInsetY = Math.max(0, (rect.h - minEdgeH) / 2)
  return {
    x: Math.min(Math.min(0.02, rect.w * 0.18), maxInsetX),
    y: Math.min(Math.min(0.02, rect.h * 0.18), maxInsetY),
  }
}

/** 排序柄放在块外，避免压住窄 KPI 左侧数字 */
export function gripOffsetStyle(rect: RectLike): CSSProperties {
  const gripPx = 22
  // 贴左边时改放到上方，防止柄本身被画布裁掉
  if (rect.x < 0.04) {
    return {
      left: `calc(${rect.x * 100}% + 3px)`,
      top: `calc(${rect.y * 100}% - ${gripPx}px)`,
    }
  }
  return {
    left: `calc(${rect.x * 100}% - ${gripPx}px)`,
    top: `calc(${rect.y * 100}% + 3px)`,
  }
}

/** 四条边手柄：左/上取相邻的前一条分隔线，右/下取后一条 */
const EDGE_HANDLES: {
  key: string
  axis: 'x' | 'y'
  side: ResizeSide
  title: string
  className: string
  barClassName: string
  style: (rect: RectLike) => CSSProperties
}[] = [
  {
    key: 'top',
    axis: 'y',
    side: 'before',
    title: '拖动调整高度',
    className: 'h-3 -translate-y-1/2 cursor-row-resize',
    barClassName: 'h-1 w-9 rounded-full bg-accent/75 shadow-sm',
    style: (rect) => {
      const inset = edgeCornerInset(rect)
      return {
        left: pct(rect.x + inset.x),
        top: pct(rect.y),
        width: pct(Math.max(rect.w - 2 * inset.x, 0)),
      }
    },
  },
  {
    key: 'bottom',
    axis: 'y',
    side: 'after',
    title: '拖动调整高度',
    className: 'h-3 -translate-y-1/2 cursor-row-resize',
    barClassName: 'h-1 w-9 rounded-full bg-accent/75 shadow-sm',
    style: (rect) => {
      const inset = edgeCornerInset(rect)
      return {
        left: pct(rect.x + inset.x),
        top: pct(rect.y + rect.h),
        width: pct(Math.max(rect.w - 2 * inset.x, 0)),
      }
    },
  },
  {
    key: 'left',
    axis: 'x',
    side: 'before',
    title: '拖动调整宽度',
    className: 'w-3 -translate-x-1/2 cursor-col-resize',
    barClassName: 'h-9 w-1 rounded-full bg-accent/75 shadow-sm',
    style: (rect) => {
      const inset = edgeCornerInset(rect)
      return {
        left: pct(rect.x),
        top: pct(rect.y + inset.y),
        height: pct(Math.max(rect.h - 2 * inset.y, 0)),
      }
    },
  },
  {
    key: 'right',
    axis: 'x',
    side: 'after',
    title: '拖动调整宽度',
    className: 'w-3 -translate-x-1/2 cursor-col-resize',
    barClassName: 'h-9 w-1 rounded-full bg-accent/75 shadow-sm',
    style: (rect) => {
      const inset = edgeCornerInset(rect)
      return {
        left: pct(rect.x + rect.w),
        top: pct(rect.y + inset.y),
        height: pct(Math.max(rect.h - 2 * inset.y, 0)),
      }
    },
  },
]

/** 四角手柄：同时开横纵两条分隔线 */
const CORNER_HANDLES: {
  key: string
  sideX: ResizeSide
  sideY: ResizeSide
  className: string
  style: (rect: RectLike) => CSSProperties
}[] = [
  {
    key: 'nw',
    sideX: 'before',
    sideY: 'before',
    className: 'cursor-nwse-resize',
    style: (rect) => ({ left: pct(rect.x), top: pct(rect.y) }),
  },
  {
    key: 'ne',
    sideX: 'after',
    sideY: 'before',
    className: 'cursor-nesw-resize',
    style: (rect) => ({ left: pct(rect.x + rect.w), top: pct(rect.y) }),
  },
  {
    key: 'sw',
    sideX: 'before',
    sideY: 'after',
    className: 'cursor-nesw-resize',
    style: (rect) => ({ left: pct(rect.x), top: pct(rect.y + rect.h) }),
  },
  {
    key: 'se',
    sideX: 'after',
    sideY: 'after',
    className: 'cursor-nwse-resize',
    style: (rect) => ({ left: pct(rect.x + rect.w), top: pct(rect.y + rect.h) }),
  },
]

const NUDGE_DIRECTIONS: Record<string, [number, number]> = {
  ArrowLeft: [-1, 0],
  ArrowRight: [1, 0],
  ArrowUp: [0, -1],
  ArrowDown: [0, 1],
}

const NUDGE_STEP_PT = 1
const NUDGE_COARSE_STEP_PT = 10
/** 连续按键合并成一次保存与一条撤销记录 */
const NUDGE_FLUSH_MS = 260
/** 缩放 / 插入：小于该像素位移视为点击，不改树或不落拖放 */
const DRAG_ACTIVATE_PX = 3

function isTextEntryTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false
  if (target.isContentEditable) return true
  return ['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName)
}

function movedPastThreshold(
  startClientX: number,
  startClientY: number,
  clientX: number,
  clientY: number,
): boolean {
  const dx = clientX - startClientX
  const dy = clientY - startClientY
  return dx * dx + dy * dy >= DRAG_ACTIVATE_PX * DRAG_ACTIVATE_PX
}

/** 按首段位移锁定缩放主轴；明显对角线才双轴 */
function resolveAxisLock(dx: number, dy: number): 'x' | 'y' | 'both' {
  const adx = Math.abs(dx)
  const ady = Math.abs(dy)
  if (adx < 1e-6 && ady < 1e-6) return 'y'
  const dominant = Math.max(adx, ady)
  const minor = Math.min(adx, ady)
  if (minor / dominant >= AXIS_DIAGONAL_MIN) return 'both'
  return ady >= adx ? 'y' : 'x'
}

/**
 * 角点专用：横向未过像素门槛强制纯 Y，避免上下拉手抖 ensure 宽度。
 */
export function resolveCornerAxisLock(dx: number, dy: number): 'x' | 'y' | 'both' {
  if (Math.abs(dx) < AXIS_X_GATE_PX) return 'y'
  return resolveAxisLock(dx, dy)
}

function ratioStartT(ratios: number[], leftIndex: number): number {
  let prefix = 0
  for (let i = 0; i <= leftIndex; i++) prefix += ratios[i] ?? 0
  return prefix / 100
}

function growStartT(grows: number[], topIndex: number): number {
  const total = grows.reduce((a, b) => a + b, 0)
  if (total <= 0) return 0.5
  let prefix = 0
  for (let i = 0; i <= topIndex; i++) prefix += grows[i] ?? 0
  return prefix / total
}

/** 内容侧保底；spacer 侧为 0，才能拖回通栏/满高原位 */
const CONTENT_SIDE_MIN = 0.05

/** 按行内分隔线拖拽结果重算 ratios（相对 startT，避免首帧跳变） */
function applyRatioDrag(base: FlexContainer, axis: RatioDragAxis, pointerX: number) {
  const row = findContainerById(base, axis.rowId)
  if (!row || row.type !== 'row') return null
  const ratios =
    row.ratios?.length === row.children.length
      ? [...row.ratios]
      : Array.from({ length: row.children.length }, () => 100 / row.children.length)
  const left = row.children[axis.leftIndex]
  const right = row.children[axis.leftIndex + 1]
  const next = ratiosFromDividerDrag({
    ratios,
    leftIndex: axis.leftIndex,
    t: axis.startT + (pointerX - axis.originX) / Math.max(axis.rowW, 1e-9),
    minLeft: left && isSpacer(left) ? 0 : CONTENT_SIDE_MIN,
    minRight: right && isSpacer(right) ? 0 : CONTENT_SIDE_MIN,
  })
  return updateRowRatios(base, axis.rowId, next)
}

/** 按列内分隔线拖拽；缺侧 wrap 外扩时上收父列 grow */
function applyGrowDrag(base: FlexContainer, axis: GrowDragAxis, pointerY: number) {
  return applyVerticalResizeDrag({
    root: base,
    columnId: axis.columnId,
    topIndex: axis.topIndex,
    colH: axis.colH,
    startT: axis.startT,
    originY: axis.originY,
    pointerY,
  })
}

/**
 * 把一次指针移动折算成新的布局树；reorder 不重排预览，返回 null。
 * 出口统一归一 grow：预览即保存后的最终形态，松手不再跳。
 */
function resolveDragTree(
  session: DragSession,
  pointer: { x: number; y: number },
): FlexContainer | null {
  const next = dragTreeDraft(session, pointer)
  return next ? normalizeGrows(next) : null
}

function dragTreeDraft(
  session: DragSession,
  pointer: { x: number; y: number },
): FlexContainer | null {
  switch (session.kind) {
    case 'ratio':
      return applyRatioDrag(session.baseTree, session, pointer.x)
    case 'grow':
      return applyGrowDrag(session.baseTree, session, pointer.y)
    case 'box': {
      const lock = session.axisLock ?? 'both'
      let tree = session.baseTree
      if (lock === 'x' || lock === 'both') {
        tree = applyRatioDrag(tree, session.x, pointer.x) ?? tree
      }
      if (lock === 'y' || lock === 'both') {
        tree = applyGrowDrag(tree, session.y, pointer.y) ?? tree
      }
      return tree
    }
    case 'offset':
      return setLeafOffset(
        session.baseTree,
        session.blockId,
        session.baseX + (pointer.x - session.startX) * CANVAS_WIDTH_PT,
        session.baseY + (pointer.y - session.startY) * CANVAS_HEIGHT_PT,
      )
    default:
      return null
  }
}

function rowSpanOf(
  baseTree: FlexContainer,
  rowId: string,
): { rowX: number; rowW: number } | null {
  const rowArea = solveNodeAreas(baseTree).get(rowId)
  if (rowArea && rowArea.w > 0) return { rowX: rowArea.x, rowW: rowArea.w }
  return null
}

/**
 * 角点拖激活：主轴为 Y 时保持纯 grow（不 ensure X）；
 * 含 X 时再补宽度对，升为 box / ratio。
 */
type ResizeDragSession = Extract<DragSession, { kind: 'ratio' | 'grow' | 'box' }>

function activateCornerGrow(
  session: Extract<DragSession, { kind: 'grow' }>,
  lock: 'x' | 'y' | 'both',
): ResizeDragSession {
  const pending = session.pendingCorner
  if (!pending) {
    return { ...session, activated: true, pendingCorner: undefined }
  }
  if (lock === 'y') {
    return {
      ...session,
      activated: true,
      pendingCorner: undefined,
      axisLock: 'y',
    }
  }

  const ensuredX = ensureResizePair(session.baseTree, pending.blockId, 'x', pending.sideX)
  if (!ensuredX) {
    return {
      ...session,
      activated: true,
      pendingCorner: undefined,
      axisLock: 'y',
    }
  }
  const xSpan = rowSpanOf(ensuredX.tree, ensuredX.containerId)
  const row = findContainerById(ensuredX.tree, ensuredX.containerId)
  if (!xSpan || !row || row.type !== 'row') {
    return {
      ...session,
      activated: true,
      pendingCorner: undefined,
      axisLock: 'y',
    }
  }
  const ratios =
    row.ratios?.length === row.children.length
      ? [...row.ratios]
      : Array.from({ length: row.children.length }, () => 100 / row.children.length)
  const xAxis: RatioDragAxis = {
    rowId: ensuredX.containerId,
    leftIndex: ensuredX.index,
    rowX: xSpan.rowX,
    rowW: xSpan.rowW,
    startT: ratioStartT(ratios, ensuredX.index),
    originX: pending.originX,
  }

  if (lock === 'x') {
    return {
      kind: 'ratio',
      baseTree: ensuredX.tree,
      ...xAxis,
      activated: true,
      deferPreview: true,
      startClientX: session.startClientX,
      startClientY: session.startClientY,
      axisLock: 'x',
    }
  }

  const column = findContainerById(ensuredX.tree, session.columnId)
  if (!column || column.type !== 'column') {
    return {
      kind: 'ratio',
      baseTree: ensuredX.tree,
      ...xAxis,
      activated: true,
      deferPreview: true,
      startClientX: session.startClientX,
      startClientY: session.startClientY,
      axisLock: 'x',
    }
  }
  const grows = column.children.map((child) => child.grow ?? 1)
  return {
    kind: 'box',
    baseTree: ensuredX.tree,
    x: xAxis,
    y: {
      columnId: session.columnId,
      topIndex: session.topIndex,
      colY: session.colY,
      colH: session.colH,
      startT: growStartT(grows, session.topIndex),
      originY: session.originY,
    },
    activated: true,
    deferPreview: true,
    startClientX: session.startClientX,
    startClientY: session.startClientY,
    axisLock: 'both',
  }
}

/**
 * flex 编辑叠加层：拖拽重排/侧栏拖入插入、行列拉伸。
 */
export function FlexEditLayer({
  projectId,
  slide,
  tree,
  selectedBlockId,
  busy,
  onPreviewTree,
  onCommitTree,
  onSelectBlock,
  onDraggingChange,
}: {
  projectId: string
  slide: DeckSlide
  tree: FlexContainer
  selectedBlockId: string | null
  /** 保存中：范围框与手柄照常显示，只是不接新手势，避免每次保存都闪一下 */
  busy?: boolean
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
  const selectedBlockIdRef = useRef(selectedBlockId)
  selectedBlockIdRef.current = selectedBlockId
  const projectIdRef = useRef(projectId)
  projectIdRef.current = projectId
  const slideIdRef = useRef(slide.id)
  slideIdRef.current = slide.id
  const busyRef = useRef(busy)
  busyRef.current = busy

  const [drag, setDrag] = useState<DragSession | null>(null)
  const [previewTree, setPreviewTree] = useState<FlexContainer | null>(null)
  const [hoveredBlockId, setHoveredBlockId] = useState<string | null>(null)
  const [hoveredDividerKey, setHoveredDividerKey] = useState<string | null>(null)

  const dragRef = useRef<DragSession | null>(null)
  dragRef.current = drag
  // 只由 showPreview / clearPreview 维护，不在 render 里回写：否则拖拽中的
  // 其它 setState 会把 ref 退回上一帧，松手提交到旧树
  const previewRef = useRef<FlexContainer | null>(null)
  /** 已提交、正等新树回到 props：期间保住预览，避免中途落回旧树 */
  const awaitCommitRef = useRef(false)

  const showPreview = (next: FlexContainer) => {
    // 同步写 ref：松手读到的必须是最后一帧，否则提交的是上一帧的树
    previewRef.current = next
    setPreviewTree(next)
    onPreviewRef.current?.(next)
  }

  const clearPreview = () => {
    awaitCommitRef.current = false
    previewRef.current = null
    setPreviewTree(null)
    onPreviewRef.current?.(null)
  }

  useEffect(() => {
    if (!awaitCommitRef.current) return
    awaitCommitRef.current = false
    previewRef.current = null
    setPreviewTree(null)
    onPreviewRef.current?.(null)
  }, [tree])

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
      let session = dragRef.current
      if (!session) return
      const pointer = toNorm(event.clientX, event.clientY)
      if (!pointer) return
      const currentTree = treeRef.current

      if (session.kind === 'reorder' || session.kind === 'insert') {
        if (session.kind === 'insert' && !session.activated) {
          if (
            !movedPastThreshold(
              session.startClientX,
              session.startClientY,
              event.clientX,
              event.clientY,
            )
          ) {
            setDrag({
              ...session,
              pointerX: pointer.x,
              pointerY: pointer.y,
            })
            return
          }
          session = { ...session, activated: true }
        }
        const drop = resolveDropTarget({
          root: currentTree,
          placements: basePlacementsRef.current,
          pointer,
          draggedBlockId: session.kind === 'reorder' ? session.blockId : null,
          mode: session.kind,
        })
        setDrag({
          ...session,
          drop,
          pointerX: pointer.x,
          pointerY: pointer.y,
        })
        return
      }

      if (
        (session.kind === 'ratio' || session.kind === 'grow' || session.kind === 'box') &&
        session.deferPreview &&
        !session.activated
      ) {
        if (
          !movedPastThreshold(
            session.startClientX,
            session.startClientY,
            event.clientX,
            event.clientY,
          )
        ) {
          return
        }
        const dx = event.clientX - session.startClientX
        const dy = event.clientY - session.startClientY
        // 角点：按主轴决定是否补 ensure X，避免纯纵向意图留下宽度包装
        let activated: ResizeDragSession
        if (session.kind === 'grow' && session.pendingCorner) {
          const adx = Math.abs(dx)
          const ady = Math.abs(dy)
          // 横向主导但未满门槛：继续等，避免 3px 激活后锁死成 Y 无法改宽
          if (adx > ady && adx < AXIS_X_GATE_PX) return
          activated = activateCornerGrow(session, resolveCornerAxisLock(dx, dy))
        } else if (session.kind === 'box') {
          activated = {
            ...session,
            activated: true,
            axisLock: resolveAxisLock(dx, dy),
          }
        } else {
          activated = { ...session, activated: true }
        }
        session = activated
        // 写穿 ref，避免连续 move 在 re-render 前重复激活、重算 lock
        dragRef.current = activated
        setDrag(activated)
        showPreview(normalizeGrows(activated.baseTree))
      }

      if (session.kind !== 'ratio' && session.kind !== 'grow' && session.kind !== 'box' && session.kind !== 'offset') {
        return
      }
      const next = resolveDragTree(session, pointer)
      if (next) showPreview(next)
    }

    /** 侧栏拖入：落点由 handlers 走服务端新建，本层没有可提交的树 */
    const runInsert = (session: Extract<DragSession, { kind: 'insert' }>) => {
      const handlers = getSlideSaveHandlers(slideIdRef.current)
      if (!handlers) return
      const anchor =
        session.activated && session.drop
          ? { parentId: session.drop.parentId, index: session.drop.index }
          : session.activated
            ? null
            : resolveInsertAnchor(treeRef.current, selectedBlockIdRef.current)
      if (!anchor) return
      const payload = session.payload
      if (payload.kind === 'block') {
        handlers.commitCreateBlock({
          type: payload.type,
          parent_id: anchor.parentId,
          index: anchor.index,
        })
        return
      }
      handlers.commitMutate((current) =>
        insertColumnsAt(projectIdRef.current, current, anchor, payload.count),
      )
    }

    /** 松手后要提交的新树；无需提交（未过阈值 / 无落点 / 插入）返回 null */
    const treeToCommit = (
      session: DragSession,
      draft: FlexContainer | null,
    ): FlexContainer | null => {
      if (session.kind === 'reorder') {
        if (!session.drop) return null
        return moveLeaf(
          treeRef.current,
          session.blockId,
          session.drop.parentId,
          session.drop.index,
        )
      }
      if (session.kind === 'insert') {
        runInsert(session)
        return null
      }
      if (session.kind !== 'offset' && session.deferPreview && !session.activated) {
        return null
      }
      return draft
    }

    const onUp = () => {
      const session = dragRef.current
      const draft = previewRef.current
      setDrag(null)
      const next = session ? treeToCommit(session, draft) : null
      if (!next) {
        clearPreview()
        return
      }
      // 预览留到提交后的新树到达再撤：立刻撤会先落回旧树，选中框闪一下
      awaitCommitRef.current = true
      onCommitRef.current(next)
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

  // 只读的悬停跟踪，保存中也继续，避免 busy 期间残留旧的悬停块
  useEffect(() => {
    const el = rootRef.current
    if (!el) return
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
  }, [])

  // 方向键微调选中块位置：1pt，按住 Shift 为 10pt
  useEffect(() => {
    if (busy || !selectedBlockId) return

    let pending: FlexContainer | null = null
    let timer: number | null = null

    const flush = () => {
      timer = null
      const next = pending
      pending = null
      if (!next) return
      awaitCommitRef.current = true
      onCommitRef.current(next)
    }

    const onKeyDown = (event: KeyboardEvent) => {
      const direction = NUDGE_DIRECTIONS[event.key]
      if (!direction) return
      if (event.metaKey || event.ctrlKey || event.altKey) return
      if (isTextEntryTarget(event.target)) return
      event.preventDefault()

      const base = pending ?? treeRef.current
      const current = leafOffset(base, selectedBlockId)
      const step = event.shiftKey ? NUDGE_COARSE_STEP_PT : NUDGE_STEP_PT
      const next = setLeafOffset(
        base,
        selectedBlockId,
        current.x + direction[0] * step,
        current.y + direction[1] * step,
      )
      if (!next) return
      pending = next
      showPreview(next)
      if (timer != null) window.clearTimeout(timer)
      timer = window.setTimeout(flush, NUDGE_FLUSH_MS)
    }

    window.addEventListener('keydown', onKeyDown)
    return () => {
      window.removeEventListener('keydown', onKeyDown)
      if (timer != null) window.clearTimeout(timer)
      flush()
    }
  }, [busy, selectedBlockId])

  const startReorder = (blockId: string, event: ReactPointerEvent) => {
    if (busy) return
    // 按住 Alt 改为像素级微调，不触发重排
    if (event.altKey) {
      startOffset(blockId, event)
      return
    }
    event.preventDefault()
    event.stopPropagation()
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
    opts?: { deferPreview?: boolean },
  ) => {
    if (busy) return
    event.preventDefault()
    event.stopPropagation()

    const span = measureRowSpan(baseTree, divider.rowId)
    if (!span) return
    const row = findContainerById(baseTree, divider.rowId)
    if (!row || row.type !== 'row') return
    const ratios =
      row.ratios?.length === row.children.length
        ? [...row.ratios]
        : Array.from({ length: row.children.length }, () => 100 / row.children.length)
    const el = rootRef.current
    if (!el) return
    const box = el.getBoundingClientRect()
    if (box.width <= 0) return
    const originX = (event.clientX - box.left) / box.width
    const deferPreview = Boolean(opts?.deferPreview)

    if (!deferPreview) showPreview(normalizeGrows(baseTree))
    setDrag({
      kind: 'ratio',
      rowId: divider.rowId,
      leftIndex: divider.leftIndex,
      rowX: span.rowX,
      rowW: span.rowW,
      baseTree,
      startT: ratioStartT(ratios, divider.leftIndex),
      originX,
      activated: !deferPreview,
      deferPreview,
      startClientX: event.clientX,
      startClientY: event.clientY,
    })
  }

  const startGrow = (
    divider: ColumnDivider,
    event: ReactPointerEvent,
    baseTree: FlexContainer = tree,
    opts?: { deferPreview?: boolean },
  ) => {
    if (busy) return
    event.preventDefault()
    event.stopPropagation()

    const span = measureColSpan(baseTree, divider.columnId)
    if (!span) return
    const column = findContainerById(baseTree, divider.columnId)
    if (!column || column.type !== 'column') return
    const grows = column.children.map((child) => child.grow ?? 1)
    const el = rootRef.current
    if (!el) return
    const box = el.getBoundingClientRect()
    if (box.height <= 0) return
    const originY = (event.clientY - box.top) / box.height
    const deferPreview = Boolean(opts?.deferPreview)

    if (!deferPreview) showPreview(normalizeGrows(baseTree))
    setDrag({
      kind: 'grow',
      columnId: divider.columnId,
      topIndex: divider.topIndex,
      colY: span.colY,
      colH: span.colH,
      baseTree,
      startT: growStartT(grows, divider.topIndex),
      originY,
      activated: !deferPreview,
      deferPreview,
      startClientX: event.clientX,
      startClientY: event.clientY,
    })
  }

  /** 选中块边手柄：先 ensure 占位块/包装，拖过阈值后再 preview */
  const beginBlockResize = (
    blockId: string,
    axis: 'x' | 'y',
    side: ResizeSide,
    event: ReactPointerEvent,
  ) => {
    if (busy) return
    const ensured = ensureResizePair(tree, blockId, axis, side)
    if (!ensured) return
    startFromPair(ensured, axis, event, { deferPreview: true })
  }

  const startFromPair = (
    pair: ResizePair,
    axis: 'x' | 'y',
    event: ReactPointerEvent,
    opts?: { deferPreview?: boolean },
  ) => {
    if (axis === 'x') {
      startRatio(
        { rowId: pair.containerId, leftIndex: pair.index, x: 0, y: 0, h: 0 },
        event,
        pair.tree,
        opts,
      )
      return
    }
    startGrow(
      { columnId: pair.containerId, topIndex: pair.index, x: 0, y: 0, w: 0 },
      event,
      pair.tree,
      opts,
    )
  }

  /**
   * 四角手柄：按下时只 ensure 纵向；激活后按主轴决定是否补横向。
   * 避免「看起来在上下拉」却已包进宽度对、左右一晃就改宽。
   */
  const beginCornerResize = (
    blockId: string,
    sideX: ResizeSide,
    sideY: ResizeSide,
    event: ReactPointerEvent,
  ) => {
    if (busy) return
    const ensuredY = ensureResizePair(tree, blockId, 'y', sideY)
    if (!ensuredY) {
      beginBlockResize(blockId, 'x', sideX, event)
      return
    }
    const span = measureColSpan(ensuredY.tree, ensuredY.containerId)
    const column = findContainerById(ensuredY.tree, ensuredY.containerId)
    if (!span || !column || column.type !== 'column') {
      beginBlockResize(blockId, 'x', sideX, event)
      return
    }
    const el = rootRef.current
    if (!el) return
    const box = el.getBoundingClientRect()
    if (box.width <= 0 || box.height <= 0) return

    event.preventDefault()
    event.stopPropagation()
    const grows = column.children.map((child) => child.grow ?? 1)
    const originX = (event.clientX - box.left) / box.width
    const originY = (event.clientY - box.top) / box.height
    setDrag({
      kind: 'grow',
      columnId: ensuredY.containerId,
      topIndex: ensuredY.index,
      colY: span.colY,
      colH: span.colH,
      baseTree: ensuredY.tree,
      startT: growStartT(grows, ensuredY.index),
      originY,
      pendingCorner: { blockId, sideX, originX },
      activated: false,
      deferPreview: true,
      startClientX: event.clientX,
      startClientY: event.clientY,
    })
  }

  /** Alt + 拖动块体：像素级平移，不参与重排 */
  const startOffset = (blockId: string, event: ReactPointerEvent) => {
    const el = rootRef.current
    if (busy || !el) return
    const box = el.getBoundingClientRect()
    if (box.width <= 0 || box.height <= 0) return
    event.preventDefault()
    event.stopPropagation()
    onSelectBlock?.(blockId)

    const base = leafOffset(tree, blockId)
    showPreview(tree)
    setDrag({
      kind: 'offset',
      blockId,
      baseTree: tree,
      baseX: base.x,
      baseY: base.y,
      startX: (event.clientX - box.left) / box.width,
      startY: (event.clientY - box.top) / box.height,
    })
  }

  useEffect(() => {
    return registerInsertDragStarter(slide.id, (payload, clientX, clientY) => {
      if (busyRef.current) return
      const el = rootRef.current
      if (!el) return
      const box = el.getBoundingClientRect()
      if (box.width <= 0 || box.height <= 0) return
      const pointerX = (clientX - box.left) / box.width
      const pointerY = (clientY - box.top) / box.height
      setDrag({
        kind: 'insert',
        payload,
        drop: null,
        grabOffsetX: 0.06,
        grabOffsetY: 0.04,
        ghostW: 0.2,
        ghostH: 0.12,
        pointerX,
        pointerY,
        activated: false,
        startClientX: clientX,
        startClientY: clientY,
      })
    })
  }, [slide.id])

  const visibleHandleId = draggingBlockId ?? selectedBlockId ?? hoveredBlockId

  const ghostLabel = (() => {
    if (drag?.kind === 'insert') {
      if (drag.payload.kind === 'columns') return `${drag.payload.count} 列`
      return BLOCK_LABEL[drag.payload.type] ?? '内容块'
    }
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
  /** 保存中手柄照常画，只是不吃指针，位置因此不会闪断 */
  const hitClass = busy ? 'pointer-events-none' : 'pointer-events-auto'

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
            className={cn(
              hitClass,
              'absolute z-20 flex w-3 -translate-x-1/2 cursor-col-resize justify-center',
            )}
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
            className={cn(
              hitClass,
              'absolute z-20 flex h-3 -translate-y-1/2 cursor-row-resize items-center',
            )}
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

      {blockIds.map((blockId) => {
        if (draggingBlockId === blockId) return null
        const rect = placements.get(blockId)
        if (!rect) return null
        if (visibleHandleId !== blockId) return null
        const isSelected = selectedBlockId === blockId
        return (
          <button
            key={blockId}
            type="button"
            title="拖动排序；按住 Alt 微调位置，方向键 1pt / Shift 10pt"
            aria-label="拖动排序"
            className={cn(
              hitClass,
              'absolute z-20 grid size-5 place-items-center',
              'rounded-md border bg-surface text-ink-muted shadow-sm transition-opacity',
              'cursor-grab active:cursor-grabbing',
              isSelected
                ? 'border-accent/50 text-ink opacity-100'
                : 'border-line opacity-90 hover:opacity-100 hover:text-ink',
            )}
            style={gripOffsetStyle(rect)}
            onPointerDown={(event) => startReorder(blockId, event)}
          >
            <GripVertical className="size-3" />
          </button>
        )
      })}

      {selectedBlockId &&
        selectedRect &&
        (drag?.kind === 'grow' || drag?.kind === 'box' || drag?.kind === 'ratio') &&
        drag.activated && (
          <div
            aria-hidden
            className="pointer-events-none absolute z-[25] rounded-sm border border-accent/55 bg-accent/5"
            style={{
              left: pct(selectedRect.x),
              top: pct(selectedRect.y),
              width: pct(selectedRect.w),
              height: pct(selectedRect.h),
            }}
          />
        )}

      {selectedBlockId && selectedRect && !dragging && (
        <>
          {selectedRect.w >= NARROW_BLOCK_HIDE_CORNER &&
            CORNER_HANDLES.map((handle) => (
              <div
                key={handle.key}
                role="separator"
                title="拖动同时调整宽高"
                className={cn(
                  hitClass,
                  'absolute z-30 grid size-3 -translate-x-1/2 -translate-y-1/2 place-items-center',
                  handle.className,
                )}
                style={handle.style(selectedRect)}
                onPointerDown={(event) =>
                  beginCornerResize(selectedBlockId, handle.sideX, handle.sideY, event)
                }
              >
                <span className="size-2 rounded-[2px] border border-accent/70 bg-surface shadow-sm" />
              </div>
            ))}
          {/* 边手柄叠在角点之上（四角已 inset），保证上下边拖是纯纵向 */}
          {EDGE_HANDLES.map((handle) => (
            <div
              key={handle.key}
              role="separator"
              title={handle.title}
              className={cn(
                hitClass,
                'absolute z-[31] flex items-center justify-center',
                handle.className,
              )}
              style={handle.style(selectedRect)}
              onPointerDown={(event) =>
                beginBlockResize(selectedBlockId, handle.axis, handle.side, event)
              }
            >
              <span className={handle.barClassName} />
            </div>
          ))}
        </>
      )}

      {(drag?.kind === 'reorder' || (drag?.kind === 'insert' && drag.activated)) && (
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

      {(drag?.kind === 'reorder' || (drag?.kind === 'insert' && drag.activated)) &&
        drag.drop && (
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
    </div>
  )
}
