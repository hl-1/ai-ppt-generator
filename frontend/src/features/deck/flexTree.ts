import {
  solveNodeAreas,
  type FlexContainer,
  type FlexLeaf,
  type FlexNode,
  type GroupPreset,
} from '@/render/flexLayout'

export const RATIO_SNAP_TOKENS = [33, 38, 50, 62, 67] as const

/**
 * 与 backend/app/domain/flex_normalize.py 的同名常量保持一致。
 * 不一致会导致拖拽结果在保存后被服务端改写。
 */
export const RATIO_SNAP_TOLERANCE = 2.5
export const GROW_MIN = 0.25
/** 编辑态拉伸允许的内容侧下限（相对/绝对值）；过小会被后端 normalize 抬回 GROW_MIN */
export const GROW_SOFT_MIN = 0.05
export const GROW_MAX = 4
export const OFFSET_LIMIT_PT = 960

/**
 * 内容块之间拖分隔线时的最小占比（避免把真内容挤没）。
 * 缺侧拉伸插入的 spacer 用 SPACER_SEED_*，且拖拽时占位侧可收到 0，才能拉回原位。
 */
export const MIN_RATIO = 8
/** 缺侧 ensure 时 spacer 的初始占比：接近 0，避免一点击/一激活就缩一截 */
export const SPACER_SEED_RATIO = 0.01
/** 缺侧 ensure 时 spacer 的初始 grow */
export const SPACER_SEED_GROW = 0.001

export type FlexBlockType =
  | 'text'
  | 'bullets'
  | 'image'
  | 'chart'
  | 'table'
  | 'kpi'
  | 'cards'
  | 'callout'

function isLeaf(node: FlexNode): node is FlexLeaf {
  return node.type === 'block'
}

function isContainer(node: FlexNode): node is FlexContainer {
  return node.type === 'row' || node.type === 'column'
}

export function cloneTree(tree: FlexContainer): FlexContainer {
  return structuredClone(tree)
}

export function newNodeId(prefix: string): string {
  return `${prefix}-${crypto.randomUUID().replace(/-/g, '').slice(0, 10)}`
}

/** 在树中定位叶子及其父容器 */
export function findLeafParent(
  root: FlexContainer,
  blockId: string,
): { parent: FlexContainer; index: number; leaf: FlexLeaf } | null {
  for (let index = 0; index < root.children.length; index++) {
    const child = root.children[index]!
    if (isLeaf(child) && child.block_id === blockId) {
      return { parent: root, index, leaf: child }
    }
    if (isContainer(child)) {
      const found = findLeafParent(child, blockId)
      if (found) return found
    }
  }
  return null
}

/** 插入目标：选中块的父容器，否则根 */
export function resolveInsertParentId(
  root: FlexContainer,
  selectedBlockId: string | null,
): string {
  if (!selectedBlockId) return root.id
  const found = findLeafParent(root, selectedBlockId)
  return found?.parent.id ?? root.id
}

/** 侧栏插入：选中块之后；无选中则根容器末尾 */
export function resolveInsertAnchor(
  root: FlexContainer,
  selectedBlockId: string | null,
): { parentId: string; index: number } {
  if (selectedBlockId) {
    const found = findLeafParent(root, selectedBlockId)
    if (found) {
      return { parentId: found.parent.id, index: found.index + 1 }
    }
  }
  return { parentId: root.id, index: root.children.length }
}

export function findContainerById(
  root: FlexContainer,
  containerId: string,
): FlexContainer | null {
  if (root.id === containerId) return root
  for (const child of root.children) {
    if (isContainer(child)) {
      const found = findContainerById(child, containerId)
      if (found) return found
    }
  }
  return null
}

export function firstLeafBlockId(node: FlexNode): string | null {
  if (isLeaf(node)) return node.block_id
  for (const child of node.children) {
    const id = firstLeafBlockId(child)
    if (id) return id
  }
  return null
}

export function iterLeaves(node: FlexNode): FlexLeaf[] {
  if (isLeaf(node)) return [node]
  return node.children.flatMap(iterLeaves)
}

/** 不可变：从树中移除叶子并返回被移除节点 */
export function removeLeafImmutable(
  root: FlexContainer,
  blockId: string,
): { tree: FlexContainer; leaf: FlexLeaf | null } {
  const tree = cloneTree(root)
  const found = findLeafParent(tree, blockId)
  if (!found) return { tree, leaf: null }
  const [leaf] = found.parent.children.splice(found.index, 1) as [FlexLeaf]
  return { tree, leaf }
}

/** 不可变：在父容器 index 处插入叶子 */
export function insertLeafImmutable(
  root: FlexContainer,
  parentId: string,
  index: number,
  leaf: FlexLeaf,
): FlexContainer | null {
  const tree = cloneTree(root)
  const parent = findContainerById(tree, parentId)
  if (!parent) return null
  const clamped = Math.max(0, Math.min(index, parent.children.length))
  parent.children.splice(clamped, 0, leaf)
  return tree
}

function rowRatios(parent: FlexContainer): number[] {
  const n = parent.children.length
  if (n <= 0) return []
  if (parent.ratios != null && parent.ratios.length === n) return [...parent.ratios]
  return Array.from({ length: n }, () => 100 / n)
}

function pickSpacerIndex(parent: FlexContainer, preferNear: number): number {
  let best = -1
  let bestGrow = -1
  for (let i = 0; i < parent.children.length; i++) {
    const child = parent.children[i]!
    if (!isSpacer(child)) continue
    const grow = child.grow ?? 1
    const near = i === preferNear || i === preferNear - 1
    if (near) return i
    if (grow > bestGrow) {
      bestGrow = grow
      best = i
    }
  }
  return best
}

/**
 * 将 block 移到目标容器的 index。
 * 同父：只换序，不改 grow/ratios。
 * 跨父：原位留等权 spacer，目标优先吃掉 spacer，避免内容块因换位变形。
 */
export function moveLeaf(
  root: FlexContainer,
  blockId: string,
  targetParentId: string,
  index: number,
): FlexContainer | null {
  const origin = findLeafParent(root, blockId)
  if (!origin) return null

  if (origin.parent.id === targetParentId) {
    return moveLeafSameParent(root, blockId, index)
  }
  return moveLeafAcrossParents(root, blockId, targetParentId, index)
}

function moveLeafSameParent(
  root: FlexContainer,
  blockId: string,
  index: number,
): FlexContainer | null {
  const tree = cloneTree(root)
  const found = findLeafParent(tree, blockId)
  if (!found) return null
  const parent = found.parent
  let insertAt = index
  if (found.index < index) insertAt -= 1
  insertAt = Math.max(0, Math.min(insertAt, parent.children.length - 1))
  if (insertAt === found.index) return null

  const ratios = parent.type === 'row' ? rowRatios(parent) : null
  const [leaf] = parent.children.splice(found.index, 1) as [FlexLeaf]
  const takenRatio = ratios ? ratios.splice(found.index, 1)[0]! : null
  parent.children.splice(insertAt, 0, leaf)
  if (ratios && takenRatio != null) {
    ratios.splice(insertAt, 0, takenRatio)
    parent.ratios = ratios
  }
  return tree
}

function moveLeafAcrossParents(
  root: FlexContainer,
  blockId: string,
  targetParentId: string,
  index: number,
): FlexContainer | null {
  const tree = cloneTree(root)
  const src = findLeafParent(tree, blockId)
  if (!src) return null
  const target = findContainerById(tree, targetParentId)
  if (!target) return null

  const leafGrow = src.leaf.grow ?? 1
  const srcParent = src.parent
  const srcIndex = src.index

  // 原位：叶子换成等权 spacer，保留 grow / ratio，其它兄弟尺寸不变
  if (srcParent.type === 'row') {
    const ratios = rowRatios(srcParent)
    const [leaf] = srcParent.children.splice(srcIndex, 1) as [FlexLeaf]
    const leafRatio = ratios.splice(srcIndex, 1)[0] ?? 100 / Math.max(ratios.length + 1, 1)
    const spacer = makeSpacer(leafGrow)
    srcParent.children.splice(srcIndex, 0, spacer)
    ratios.splice(srcIndex, 0, leafRatio)
    srcParent.ratios = ratios
    return placeLeafAtTarget(tree, target, index, leaf, leafGrow, leafRatio)
  }

  const [leaf] = srcParent.children.splice(srcIndex, 1) as [FlexLeaf]
  srcParent.children.splice(srcIndex, 0, makeSpacer(leafGrow))
  return placeLeafAtTarget(tree, target, index, leaf, leafGrow, null)
}

function renormalizeRatios(ratios: number[]): number[] {
  const total = ratios.reduce((sum, value) => sum + value, 0) || 1
  return ratios.map((value) => (value / total) * 100)
}

function placeLeafAtTarget(
  tree: FlexContainer,
  target: FlexContainer,
  index: number,
  leaf: FlexLeaf,
  leafGrow: number,
  leafRatio: number | null,
): FlexContainer {
  leaf.grow = leafGrow
  const insertAt = Math.max(0, Math.min(index, target.children.length))
  const spacerIndex = pickSpacerIndex(target, insertAt)

  if (spacerIndex >= 0) {
    const spacer = target.children[spacerIndex] as FlexContainer
    const spacerGrow = spacer.grow ?? 1

    // spacer 权重大致够：直接替换，内容兄弟权重不动
    if (spacerGrow <= leafGrow + 1e-6) {
      if (target.type === 'row') {
        const ratios = rowRatios(target)
        ratios[spacerIndex] = leafRatio ?? ratios[spacerIndex]!
        target.ratios = renormalizeRatios(ratios)
      }
      target.children.splice(spacerIndex, 1, leaf)
      return tree
    }

    // spacer 更大：扣减后在落点插入叶子
    spacer.grow = Math.max(0.25, spacerGrow - leafGrow)
    if (target.type === 'row') {
      const ratios = rowRatios(target)
      const spacerRatio = ratios[spacerIndex]!
      const take =
        leafRatio != null ? Math.min(leafRatio, spacerRatio * 0.9) : spacerRatio / 2
      ratios[spacerIndex] = Math.max(5, spacerRatio - take)
      let place = Math.max(0, Math.min(insertAt, target.children.length))
      target.children.splice(place, 0, leaf)
      ratios.splice(place, 0, Math.max(5, take))
      target.ratios = renormalizeRatios(ratios)
      return tree
    }
    const place = Math.max(0, Math.min(insertAt, target.children.length))
    target.children.splice(place, 0, leaf)
    return tree
  }

  // 无 spacer：保留原 grow 插入，不对邻居对半拆分
  if (target.type === 'row') {
    const ratios = rowRatios(target)
    const share =
      leafRatio != null && leafRatio > 0
        ? leafRatio
        : 100 / Math.max(target.children.length + 1, 1)
    target.children.splice(insertAt, 0, leaf)
    ratios.splice(insertAt, 0, share)
    target.ratios = renormalizeRatios(ratios)
    return tree
  }
  target.children.splice(insertAt, 0, leaf)
  return tree
}

/** 把若干同级叶子包进 row → 每列一个 column → 叶子 */
export function wrapBlockIdsAsColumns(
  root: FlexContainer,
  blockIds: string[],
): FlexContainer | null {
  if (blockIds.length < 2) return null
  const tree = cloneTree(root)
  const locations = blockIds.map((id) => findLeafParent(tree, id))
  if (locations.some((loc) => loc == null)) return null
  const parent = locations[0]!.parent
  if (locations.some((loc) => loc!.parent.id !== parent.id)) return null

  const indices = locations.map((loc) => loc!.index).sort((a, b) => a - b)
  // 必须连续同级
  for (let i = 1; i < indices.length; i++) {
    if (indices[i] !== indices[i - 1]! + 1) return null
  }

  const leaves = indices.map((i) => parent.children[i] as FlexLeaf)
  const start = indices[0]!
  parent.children.splice(start, leaves.length)

  const columns: FlexContainer[] = leaves.map((leaf) => ({
    type: 'column',
    id: newNodeId('col'),
    children: [leaf],
    gap_pt: 16,
    grow: 1,
  }))

  const row: FlexContainer = {
    type: 'row',
    id: newNodeId('row'),
    children: columns,
    gap_pt: 16,
    ratios: Array.from({ length: columns.length }, () => 100 / columns.length),
    grow: 1,
  }
  parent.children.splice(start, 0, row)
  return tree
}

export function updateRowRatios(
  root: FlexContainer,
  rowId: string,
  ratios: number[],
): FlexContainer | null {
  const tree = cloneTree(root)
  const row = findContainerById(tree, rowId)
  if (!row || row.type !== 'row') return null
  row.ratios = ratios
  return tree
}

/** 不可变：更新 column 子节点 grow 权重 */
export function updateChildGrows(
  root: FlexContainer,
  containerId: string,
  grows: number[],
): FlexContainer | null {
  const tree = cloneTree(root)
  const container = findContainerById(tree, containerId)
  if (!container || container.type !== 'column') return null
  if (grows.length !== container.children.length) return null
  for (let i = 0; i < container.children.length; i++) {
    const child = container.children[i]!
    // spacer → 0；内容侧用软下限，拉伸时才能从兄弟多偷一点高度
    const floor = isSpacer(child) ? 0 : GROW_SOFT_MIN
    child.grow = Math.min(GROW_MAX, Math.max(floor, grows[i]!))
  }
  return tree
}

/** 不可变：设置容器预设皮肤；preset=null 清除 */
export function setContainerPreset(
  root: FlexContainer,
  containerId: string,
  preset: GroupPreset | null,
): FlexContainer | null {
  const tree = cloneTree(root)
  const container = findContainerById(tree, containerId)
  if (!container) return null
  container.preset = preset
  return tree
}

/**
 * 双列在靠近 33/38/50/62/67 时吸附，否则保留精确比例；多列仅归一化到 100。
 * 无条件吸附会让拖动只有几个离散档位，手感上就是跳。
 */
export function snapRatios(ratios: number[]): number[] {
  const n = ratios.length
  if (n <= 0) return ratios
  if (n === 2) {
    const total = ratios[0]! + ratios[1]!
    if (total <= 0) return [50, 50]
    const pct = sumsTo100(total) ? ratios[0]! : (ratios[0]! / total) * 100
    const pairs = RATIO_SNAP_TOKENS.flatMap((a) =>
      RATIO_SNAP_TOKENS.filter((b) => Math.abs(a + b - 100) < 1e-9).map(
        (b) => [a, b] as const,
      ),
    )
    const best = pairs.reduce((acc, pair) =>
      Math.abs(pair[0] - pct) < Math.abs(acc[0] - pct) ? pair : acc,
    )
    if (Math.abs(best[0] - pct) <= RATIO_SNAP_TOLERANCE) {
      return [best[0], best[1]]
    }
    return [pct, 100 - pct]
  }
  const sum = ratios.reduce((a, b) => a + b, 0)
  if (sum <= 0) return Array.from({ length: n }, () => 100 / n)
  if (sumsTo100(sum)) return [...ratios]
  return ratios.map((r) => (r / sum) * 100)
}

/** 已经以 100 为基准时跳过除乘，避免每次保存都引入浮点抖动 */
function sumsTo100(total: number): boolean {
  return Math.abs(total - 100) < 1e-9
}

/** 拖动第 leftIndex|leftIndex+1 分隔线时，按归一化 x 重算整行 ratios */
export function ratiosFromDividerDrag(args: {
  ratios: number[]
  leftIndex: number
  /** 指针在行内容区的相对位置 0..1 */
  t: number
  /**
   * 左/右侧在 pair 内的最小份额 0..1。
   * spacer 侧传 0，才能拖回通栏原位；内容侧默认约 5%。
   */
  minLeft?: number
  minRight?: number
}): number[] {
  const { ratios, leftIndex, t } = args
  const n = ratios.length
  if (leftIndex < 0 || leftIndex >= n - 1) return ratios
  const minLeft = Math.max(0, args.minLeft ?? 0.05)
  const minRight = Math.max(0, args.minRight ?? 0.05)
  const clampedT = Math.max(minLeft, Math.min(1 - minRight, t))

  if (n === 2) {
    return snapRatios([clampedT * 100, (1 - clampedT) * 100])
  }

  const next = [...ratios]
  const prefix = next.slice(0, leftIndex).reduce((a, b) => a + b, 0)
  const suffix = next.slice(leftIndex + 2).reduce((a, b) => a + b, 0)
  const pairBudget = 100 - prefix - suffix
  if (pairBudget <= 0) return snapRatios(next)

  // t 是整行比例；映射到 pair 内份额
  const leftEdge = prefix / 100
  const rightEdge = (prefix + pairBudget) / 100
  const local = (clampedT - leftEdge) / Math.max(rightEdge - leftEdge, 1e-9)
  const localClamped = Math.max(minLeft, Math.min(1 - minRight, local))
  next[leftIndex] = pairBudget * localClamped
  next[leftIndex + 1] = pairBudget * (1 - localClamped)
  return snapRatios(next)
}

/** 拖动 column 内上下分隔线，重分配相邻 grow（总和不变） */
export function growsFromDividerDrag(args: {
  grows: number[]
  topIndex: number
  /** 指针在列内容区的相对位置 0..1 */
  t: number
  /** 上/下侧最小份额（相对 pair）；spacer 侧传 0 */
  minTop?: number
  minBottom?: number
}): number[] {
  const { grows, topIndex, t } = args
  const n = grows.length
  if (topIndex < 0 || topIndex >= n - 1) return grows
  const next = [...grows]
  const prefix = next.slice(0, topIndex).reduce((a, b) => a + b, 0)
  const suffix = next.slice(topIndex + 2).reduce((a, b) => a + b, 0)
  const pair = next[topIndex]! + next[topIndex + 1]!
  const total = prefix + pair + suffix
  if (total <= 0 || pair <= 0) return grows

  const minTop = Math.max(0, args.minTop ?? 0.05)
  const minBottom = Math.max(0, args.minBottom ?? 0.05)
  const clampedT = Math.max(minTop, Math.min(1 - minBottom, t))
  const topEdge = prefix / total
  const bottomEdge = (prefix + pair) / total
  const local =
    (clampedT - topEdge) / Math.max(bottomEdge - topEdge, 1e-9)
  const localClamped = Math.max(minTop, Math.min(1 - minBottom, local))
  // 用地板比例 * pair，避免绝对 GROW_MIN 把可偷高度卡死
  const topFloor = minTop === 0 ? 0 : pair * minTop
  const bottomFloor = minBottom === 0 ? 0 : pair * minBottom
  next[topIndex] = Math.max(topFloor, pair * localClamped)
  next[topIndex + 1] = Math.max(bottomFloor, pair * (1 - localClamped))
  return next
}

export type RowDivider = {
  rowId: string
  leftIndex: number
  /** 归一化坐标 */
  x: number
  y: number
  h: number
}

export type ColumnDivider = {
  columnId: string
  topIndex: number
  x: number
  y: number
  w: number
}

type RectLike = { x: number; y: number; w: number; h: number }

function unionRects(rects: RectLike[]): RectLike | null {
  if (rects.length === 0) return null
  let x0 = Infinity
  let y0 = Infinity
  let x1 = -Infinity
  let y1 = -Infinity
  for (const r of rects) {
    x0 = Math.min(x0, r.x)
    y0 = Math.min(y0, r.y)
    x1 = Math.max(x1, r.x + r.w)
    y1 = Math.max(y1, r.y + r.h)
  }
  return { x: x0, y: y0, w: x1 - x0, h: y1 - y0 }
}

export function isSpacer(node: FlexNode): boolean {
  return isContainer(node) && node.id.startsWith('spacer-')
}

function makeSpacer(grow = 1): FlexContainer {
  return {
    type: 'column',
    id: newNodeId('spacer'),
    children: [],
    gap_pt: 0,
    grow,
  }
}

function nodeBounds(
  node: FlexNode,
  placements: Map<string, RectLike>,
  nodeAreas?: Map<string, RectLike>,
): RectLike | null {
  if (isContainer(node) && nodeAreas?.has(node.id)) {
    return nodeAreas.get(node.id) ?? null
  }
  if (isLeaf(node)) {
    return placements.get(node.block_id) ?? nodeAreas?.get(node.id) ?? null
  }
  const rects = iterLeaves(node)
    .map((leaf) => placements.get(leaf.block_id))
    .filter((r): r is RectLike => r != null)
  return unionRects(rects) ?? (nodeAreas?.get(node.id) ?? null)
}

/** 收集所有 row 的列间分隔线几何 */
export function collectRowDividers(
  root: FlexContainer,
  placements: Map<string, RectLike>,
): RowDivider[] {
  const result: RowDivider[] = []
  const nodeAreas = solveNodeAreas(root)

  const walk = (node: FlexContainer) => {
    if (node.type === 'row' && node.children.length >= 2) {
      const bounds = node.children.map((child) =>
        nodeBounds(child, placements, nodeAreas),
      )
      for (let i = 0; i < node.children.length - 1; i++) {
        const left = bounds[i]
        const right = bounds[i + 1]
        if (!left || !right) continue
        const x = (left.x + left.w + right.x) / 2
        const y = Math.min(left.y, right.y)
        const h = Math.max(left.y + left.h, right.y + right.h) - y
        result.push({ rowId: node.id, leftIndex: i, x, y, h })
      }
    }
    for (const child of node.children) {
      if (isContainer(child)) walk(child)
    }
  }

  walk(root)
  return result
}

/** 收集 column 内行间分隔线（纵向拉伸） */
export function collectColumnDividers(
  root: FlexContainer,
  placements: Map<string, RectLike>,
): ColumnDivider[] {
  const result: ColumnDivider[] = []
  const nodeAreas = solveNodeAreas(root)

  const walk = (node: FlexContainer) => {
    if (node.type === 'column' && node.children.length >= 2) {
      const bounds = node.children.map((child) =>
        nodeBounds(child, placements, nodeAreas),
      )
      for (let i = 0; i < node.children.length - 1; i++) {
        const top = bounds[i]
        const bottom = bounds[i + 1]
        if (!top || !bottom) continue
        const y = (top.y + top.h + bottom.y) / 2
        const x = Math.min(top.x, bottom.x)
        const w = Math.max(top.x + top.w, bottom.x + bottom.w) - x
        result.push({ columnId: node.id, topIndex: i, x, y, w })
      }
    }
    for (const child of node.children) {
      if (isContainer(child)) walk(child)
    }
  }

  walk(root)
  return result
}

export type DropTarget = {
  parentId: string
  index: number
  /** 指示线：归一化 */
  line: { x: number; y: number; w: number; h: number; axis: 'x' | 'y' }
}

/**
 * 落点语义：
 * - reorder 是搬动已有块，落到内容前缘最不容易误判
 * - insert 是往空白里放新块，必须能落进尾部空白本身
 */
export type DropMode = 'insert' | 'reorder'

/** 画布内就地插入点：出现在兄弟间隙与首尾 */
export type InsertSlot = {
  parentId: string
  index: number
  /** + 按钮中心，归一化 */
  x: number
  y: number
  axis: 'x' | 'y'
}

/**
 * 收集可插入间隙。
 * 单子容器（常见列包装）不收集，避免空列两侧刷满插槽；
 * insert 模式例外，否则单块列旁的大片空白无处可落。
 * 传入 nodeAreas 后 spacer 空容器也有 bounds，空白区可作落点。
 */
export function collectInsertSlots(
  root: FlexContainer,
  placements: Map<string, RectLike>,
  nodeAreas?: Map<string, RectLike>,
  mode: DropMode = 'reorder',
): InsertSlot[] {
  const areas = nodeAreas ?? solveNodeAreas(root)
  const result: InsertSlot[] = []

  const walk = (node: FlexContainer, isRoot: boolean) => {
    const allow =
      isRoot ||
      node.children.length >= 2 ||
      (mode === 'insert' && node.children.length > 0)
    if (allow) {
      const vertical = node.type === 'column'
      const childBounds = node.children.map((child) =>
        nodeBounds(child, placements, areas),
      )
      const valid = childBounds
        .map((bounds, index) => ({ bounds, index }))
        .filter((item): item is { bounds: RectLike; index: number } => item.bounds != null)

      if (valid.length > 0) {
        const first = valid[0]!
        const last = valid[valid.length - 1]!

        if (vertical) {
          result.push({
            parentId: node.id,
            index: first.index,
            x: first.bounds.x + first.bounds.w / 2,
            y: first.bounds.y,
            axis: 'y',
          })
          for (let i = 0; i < valid.length - 1; i++) {
            const a = valid[i]!
            const b = valid[i + 1]!
            result.push({
              parentId: node.id,
              index: b.index,
              x: (a.bounds.x + a.bounds.w / 2 + b.bounds.x + b.bounds.w / 2) / 2,
              y: (a.bounds.y + a.bounds.h + b.bounds.y) / 2,
              axis: 'y',
            })
          }
          result.push({
            parentId: node.id,
            index: last.index + 1,
            x: last.bounds.x + last.bounds.w / 2,
            y: last.bounds.y + last.bounds.h,
            axis: 'y',
          })
        } else {
          result.push({
            parentId: node.id,
            index: first.index,
            x: first.bounds.x,
            y: first.bounds.y + first.bounds.h / 2,
            axis: 'x',
          })
          for (let i = 0; i < valid.length - 1; i++) {
            const a = valid[i]!
            const b = valid[i + 1]!
            result.push({
              parentId: node.id,
              index: b.index,
              x: (a.bounds.x + a.bounds.w + b.bounds.x) / 2,
              y: (a.bounds.y + a.bounds.h / 2 + b.bounds.y + b.bounds.h / 2) / 2,
              axis: 'x',
            })
          }
          result.push({
            parentId: node.id,
            index: last.index + 1,
            x: last.bounds.x + last.bounds.w,
            y: last.bounds.y + last.bounds.h / 2,
            axis: 'x',
          })
        }
      }
    }

    for (const child of node.children) {
      if (isContainer(child)) walk(child, false)
    }
  }

  walk(root, true)
  return result
}

/** 仅保留焦点块前后的插入点（静止时不铺满画布） */
export function slotsNearBlock(
  slots: InsertSlot[],
  root: FlexContainer,
  blockId: string | null,
): InsertSlot[] {
  if (!blockId) return []
  const loc = findLeafParent(root, blockId)
  if (!loc) return []
  return slots.filter(
    (slot) =>
      slot.parentId === loc.parent.id &&
      (slot.index === loc.index || slot.index === loc.index + 1),
  )
}

export type BlockResizeAxis = {
  containerId: string
  index: number
}

/** 拉伸方向：after 用右/下手柄，before 用左/上手柄 */
export type ResizeSide = 'before' | 'after'

export type ResizePair = {
  tree: FlexContainer
  containerId: string
  index: number
}

/**
 * 保证选中块在指定轴与指定侧可拉伸：必要时插入占位块或就地包一层容器。
 * 返回用于拖拽的 containerId + 分隔线左侧/上方子项 index，以及改写后的树。
 */
export function ensureResizePair(
  root: FlexContainer,
  blockId: string,
  axis: 'x' | 'y',
  side: ResizeSide = 'after',
): ResizePair | null {
  const tree = cloneTree(root)
  // 纵拉前拆掉「左右 spacer + 叶子」的宽度种子包装，避免手抖改 ratios 把窄 KPI 挤没
  if (axis === 'y') {
    unwrapSeedWidthWraps(tree, blockId)
  }
  const loc = findLeafParent(tree, blockId)
  if (!loc) return null

  if (axis === 'y') {
    return ensureHeightPair(tree, loc.parent, loc.index, loc.leaf, side)
  }
  return ensureWidthPair(tree, loc.parent, loc.index, loc.leaf, side)
}

/**
 * 若叶子被包在「仅含 spacer + 该叶子」的 row 里，上提到父级，去掉无用的宽度种子层。
 * 可叠多层（先左右再缺侧），直到父级不再是纯种子 row。
 */
function unwrapSeedWidthWraps(tree: FlexContainer, blockId: string): void {
  for (let guard = 0; guard < 6; guard++) {
    const loc = findLeafParent(tree, blockId)
    if (!loc || loc.parent.type !== 'row') return
    if (!isSeedWidthRow(loc.parent)) return
    const outer = findContainerParent(tree, loc.parent.id)
    if (!outer) return
    const wrap = loc.parent
    const leaf = loc.leaf
    leaf.grow = wrap.grow ?? leaf.grow ?? 1
    outer.parent.children[outer.index] = leaf
  }
}

/** row 子项仅为「一个内容叶子 + 若干 spacer」时视为宽度种子包装 */
function isSeedWidthRow(row: FlexContainer): boolean {
  if (row.type !== 'row' || row.gap_pt !== 0) return false
  let leaves = 0
  for (const child of row.children) {
    if (isSpacer(child)) continue
    if (child.type === 'block') {
      leaves += 1
      continue
    }
    return false
  }
  return leaves === 1 && row.children.length >= 2
}

function ensureHeightPair(
  tree: FlexContainer,
  parent: FlexContainer,
  index: number,
  leaf: FlexLeaf,
  side: ResizeSide,
): ResizePair | null {
  if (parent.type === 'column') {
    // 目标侧已有兄弟：用真分隔线。缺侧不要把 spacer 插进带 gap 的父列，
    // 否则 grow=0 仍吃掉 gap，顶/底永远回不到满高。
    if (side === 'after' && index < parent.children.length - 1) {
      return pairInContainer(tree, parent, index, side)
    }
    if (side === 'before' && index > 0) {
      return pairInContainer(tree, parent, index, side)
    }
    return wrapLeafInCell(tree, parent, index, leaf, side, 'column')
  }
  // 父为 row：同行子项共享行高，直接调行的 grow 会连带改变兄弟单元格。
  // 就地把该叶子单独包一层 column，让高度只作用于这一格。
  return wrapLeafInCell(tree, parent, index, leaf, side, 'column')
}

function ensureWidthPair(
  tree: FlexContainer,
  parent: FlexContainer,
  index: number,
  leaf: FlexLeaf,
  side: ResizeSide,
): ResizePair | null {
  if (parent.type === 'row') {
    return pairInContainer(tree, parent, index, side)
  }
  // 通栏列、或先 ensure 高度后的 [内容|spacer] cell：宽度打到外层 row，
  // 避免再包一层 seed row 导致「上下拖」误改内层宽度。
  const outer = findContainerParent(tree, parent.id)
  if (outer?.parent.type === 'row' && isTrivialWidthColumn(parent)) {
    return pairInContainer(tree, outer.parent, outer.index, side)
  }
  return wrapLeafInCell(tree, parent, index, leaf, side, 'row')
}

/** 单子通栏列，或高度包装 cell（gap=0 且含 spacer） */
function isTrivialWidthColumn(column: FlexContainer): boolean {
  if (column.type !== 'column') return false
  if (column.children.length === 1) return true
  if (column.gap_pt === 0 && column.children.length === 2) {
    return column.children.some((child) => isSpacer(child))
  }
  return false
}

/** 就地把叶子包进一个只含它与占位块的容器，让拉伸只作用于这一格 */
function wrapLeafInCell(
  tree: FlexContainer,
  parent: FlexContainer,
  index: number,
  leaf: FlexLeaf,
  side: ResizeSide,
  type: 'row' | 'column',
): ResizePair | null {
  const sized: FlexLeaf = { ...leaf, grow: type === 'column' ? GROW_MAX : (leaf.grow ?? 1) }
  const spacer = makeSpacer(type === 'column' ? SPACER_SEED_GROW : 1)
  const cell: FlexContainer = {
    type,
    id: newNodeId('cell'),
    gap_pt: 0,
    grow: parent.children[index]?.grow ?? 1,
    children: side === 'before' ? [spacer, sized] : [sized, spacer],
    ratios:
      type === 'row'
        ? side === 'before'
          ? [SPACER_SEED_RATIO, 100 - SPACER_SEED_RATIO]
          : [100 - SPACER_SEED_RATIO, SPACER_SEED_RATIO]
        : null,
  }
  parent.children[index] = cell
  return { tree, containerId: cell.id, index: 0 }
}

/**
 * 在容器内为第 index 项取一条可拖的分隔线：
 * 目标侧已有兄弟就直接用相邻分隔线，否则补一个最小份额占位块。
 */
function pairInContainer(
  tree: FlexContainer,
  container: FlexContainer,
  index: number,
  side: ResizeSide,
): ResizePair | null {
  if (side === 'after' && index < container.children.length - 1) {
    return { tree, containerId: container.id, index }
  }
  if (side === 'before' && index > 0) {
    return { tree, containerId: container.id, index: index - 1 }
  }
  if (!insertSpacerSharing(container, index, side === 'after' ? index + 1 : index)) {
    return null
  }
  return { tree, containerId: container.id, index }
}

/** 在 at 处插入占位块，只扣种子份额，几何几乎不变；拖动后再拉开 */
function insertSpacerSharing(
  container: FlexContainer,
  unitIndex: number,
  at: number,
): boolean {
  const unit = container.children[unitIndex]
  if (!unit) return false

  if (container.type === 'row') {
    const count = container.children.length
    const ratios =
      container.ratios?.length === count
        ? [...container.ratios]
        : Array.from({ length: count }, () => 100 / count)
    const current = ratios[unitIndex] ?? 100 / count
    const take = Math.min(SPACER_SEED_RATIO, Math.max(current / 2, SPACER_SEED_RATIO))
    ratios[unitIndex] = Math.max(current - take, SPACER_SEED_RATIO)
    ratios.splice(at, 0, take)
    container.children.splice(at, 0, makeSpacer(1))
    container.ratios = normalizeRatioSum(ratios)
    return true
  }

  const current = unit.grow ?? 1
  const take = Math.min(SPACER_SEED_GROW, Math.max(current / 2, SPACER_SEED_GROW))
  unit.grow = Math.max(current - take, SPACER_SEED_GROW)
  container.children.splice(at, 0, makeSpacer(take))
  return true
}

function normalizeRatioSum(ratios: number[]): number[] {
  const total = ratios.reduce((a, b) => a + b, 0)
  if (total <= 0) return ratios.map(() => 100 / ratios.length)
  return ratios.map((r) => (r / total) * 100)
}

/** 读取叶子当前的像素级偏移 */
export function leafOffset(root: FlexContainer, blockId: string): { x: number; y: number } {
  for (const leaf of iterLeaves(root)) {
    if (leaf.block_id === blockId) {
      return { x: leaf.offset_x_pt ?? 0, y: leaf.offset_y_pt ?? 0 }
    }
  }
  return { x: 0, y: 0 }
}

/**
 * 设置叶子的像素级偏移（绝对值，pt）。
 * 只挪位置不改尺寸，越界由 solver 钳制。
 */
export function setLeafOffset(
  root: FlexContainer,
  blockId: string,
  xPt: number,
  yPt: number,
): FlexContainer | null {
  const tree = cloneTree(root)
  const loc = findLeafParent(tree, blockId)
  if (!loc) return null
  const leaf = loc.parent.children[loc.index]
  if (!leaf || !isLeaf(leaf)) return null
  leaf.offset_x_pt = clampOffset(xPt)
  leaf.offset_y_pt = clampOffset(yPt)
  return tree
}

function clampOffset(value: number): number {
  const rounded = Math.round(value * 100) / 100
  return Math.min(OFFSET_LIMIT_PT, Math.max(-OFFSET_LIMIT_PT, rounded))
}

/** 内容侧分隔线保底份额；spacer 侧用 0 */
const CONTENT_SIDE_MIN = GROW_SOFT_MIN

/**
 * 从 startId 向上找最近的、可偷兄弟的 column 祖先。
 * expandDown：优先能偷下方（footer），否则偷上方；expandUp 相反。
 */
function findBubbleColumn(
  root: FlexContainer,
  startId: string,
  expandDown: boolean,
): { columnId: string; branchIndex: number } | null {
  let loc = findContainerParent(root, startId)
  while (loc) {
    if (loc.parent.type === 'column' && loc.parent.children.length >= 2) {
      const canStealBelow = loc.index < loc.parent.children.length - 1
      const canStealAbove = loc.index > 0
      if (expandDown ? canStealBelow || canStealAbove : canStealAbove || canStealBelow) {
        return { columnId: loc.parent.id, branchIndex: loc.index }
      }
    }
    loc = findContainerParent(root, loc.parent.id)
  }
  return null
}

/** 触底后沿祖先 column 逐级偷高，直到位移耗尽或无更多兄弟可偷 */
function cascadeBubbleGrow(args: {
  tree: FlexContainer
  startId: string
  remainingY: number
  expandDown: boolean
  colH: number
}): FlexContainer | null {
  let tree = args.tree
  let remainingY = args.remainingY
  let cursorId = args.startId
  for (let guard = 0; guard < 8 && Math.abs(remainingY) > 1e-5; guard++) {
    const bubble = findBubbleColumn(tree, cursorId, args.expandDown)
    if (!bubble) break
    const beforeH = branchNormH(tree, bubble.columnId, bubble.branchIndex)
    const next = applyBubbleGrow({
      tree,
      columnId: bubble.columnId,
      branchIndex: bubble.branchIndex,
      deltaY: remainingY,
      expandDown: args.expandDown,
      colH: args.colH,
    })
    if (!next) break
    const afterH = branchNormH(next, bubble.columnId, bubble.branchIndex)
    const gained = afterH - beforeH
    tree = next
    if (Math.abs(gained) <= 1e-6) break
    // 下扩 gained>0；上扩 branch 变高时 gained 亦 >0，remainingY 为负则加上 gained 向 0 收敛
    remainingY = args.expandDown ? remainingY - gained : remainingY + gained
    cursorId = bubble.columnId
  }
  return tree
}

function branchNormH(
  tree: FlexContainer,
  columnId: string,
  branchIndex: number,
): number {
  const column = findContainerById(tree, columnId)
  const area = solveNodeAreas(tree).get(columnId)
  if (!column || !area) return 0
  const grows = column.children.map((child) => child.grow ?? 1)
  const total = grows.reduce((a, b) => a + b, 0)
  if (total <= 0) return 0
  return ((grows[branchIndex] ?? 0) / total) * area.h
}

function applyBubbleGrow(args: {
  tree: FlexContainer
  columnId: string
  branchIndex: number
  /** 指针相对 origin 的位移（归一化）；下为正 */
  deltaY: number
  expandDown: boolean
  colH: number
}): FlexContainer | null {
  const { tree, columnId, branchIndex, deltaY, expandDown, colH } = args
  const column = findContainerById(tree, columnId)
  if (!column || column.type !== 'column') return null
  const grows = column.children.map((child) => child.grow ?? 1)
  const parentArea = solveNodeAreas(tree).get(columnId)
  const parentH = parentArea?.h ?? colH

  // 下扩：先偷下方兄弟（增大 branch、减小 below），否则偷上方
  // 上扩：先偷上方，否则偷下方
  let topIndex: number
  let invert: boolean
  if (expandDown) {
    if (branchIndex < grows.length - 1) {
      topIndex = branchIndex
      invert = false // 指针下移 → t 增大 → 上方(branch)变大
    } else if (branchIndex > 0) {
      topIndex = branchIndex - 1
      invert = true // 指针下移 → t 减小 → 下方(branch)变大
    } else {
      return null
    }
  } else if (branchIndex > 0) {
    topIndex = branchIndex - 1
    invert = false // 指针上移 deltaY<0 → t 减小 → 上方变小、branch 变大… 需 invert
    // 上扩：指针上移应增大下方 branch。topIndex=branch-1，减小 t → 上方变小、下方变大。
    // parentT = startT + deltaY/H；deltaY<0 → t 降 → 下方变大。invert=false ✓
  } else if (branchIndex < grows.length - 1) {
    topIndex = branchIndex
    invert = true
  } else {
    return null
  }

  const startParentT = growStartT(grows, topIndex)
  const parentT = invert
    ? startParentT - deltaY / Math.max(parentH, 1e-9)
    : startParentT + deltaY / Math.max(parentH, 1e-9)
  return updateChildGrows(
    tree,
    columnId,
    growsFromDividerDrag({
      grows,
      topIndex,
      t: parentT,
      minTop: CONTENT_SIDE_MIN,
      minBottom: CONTENT_SIDE_MIN,
    }),
  )
}

/**
 * 纵向边拖：先改 column 内相邻 grow；
 * 邻侧已触底（spacer=0 或内容软下限）仍继续外扩时，沿祖先 column 偷兄弟高度。
 */
export function applyVerticalResizeDrag(args: {
  root: FlexContainer
  columnId: string
  topIndex: number
  colH: number
  startT: number
  originY: number
  pointerY: number
}): FlexContainer | null {
  const { root, columnId, topIndex, colH, startT, originY, pointerY } = args
  const column = findContainerById(root, columnId)
  if (!column || column.type !== 'column') return null
  const top = column.children[topIndex]
  const bottom = column.children[topIndex + 1]
  if (!top || !bottom) return null

  const minTop = isSpacer(top) ? 0 : CONTENT_SIDE_MIN
  const minBottom = isSpacer(bottom) ? 0 : CONTENT_SIDE_MIN
  const t = startT + (pointerY - originY) / Math.max(colH, 1e-9)
  const grows = column.children.map((child) => child.grow ?? 1)
  const maxT = 1 - minBottom
  const minT = minTop

  // 底边外扩超过本对可给额度 → 邻侧触底后沿祖先逐级偷高
  if (t > maxT) {
    let tree = updateChildGrows(
      root,
      columnId,
      growsFromDividerDrag({
        grows,
        topIndex,
        t: maxT,
        minTop,
        minBottom,
      }),
    )
    if (!tree) return null
    return (
      cascadeBubbleGrow({
        tree,
        startId: columnId,
        remainingY: (t - maxT) * colH,
        expandDown: true,
        colH,
      }) ?? tree
    )
  }

  // 顶边外扩超过本对可给额度
  if (t < minT) {
    let tree = updateChildGrows(
      root,
      columnId,
      growsFromDividerDrag({
        grows,
        topIndex,
        t: minT,
        minTop,
        minBottom,
      }),
    )
    if (!tree) return null
    return (
      cascadeBubbleGrow({
        tree,
        startId: columnId,
        remainingY: (t - minT) * colH,
        expandDown: false,
        colH,
      }) ?? tree
    )
  }

  return updateChildGrows(
    root,
    columnId,
    growsFromDividerDrag({
      grows,
      topIndex,
      t,
      minTop,
      minBottom,
    }),
  )
}

function growStartT(grows: number[], topIndex: number): number {
  const total = grows.reduce((a, b) => a + b, 0)
  if (total <= 0) return 0.5
  let prefix = 0
  for (let i = 0; i <= topIndex; i++) prefix += grows[i] ?? 0
  return prefix / total
}

export function findContainerParent(
  root: FlexContainer,
  containerId: string,
): { parent: FlexContainer; index: number } | null {
  const walk = (
    node: FlexContainer,
  ): { parent: FlexContainer; index: number } | null => {
    for (let i = 0; i < node.children.length; i++) {
      const child = node.children[i]!
      if (isContainer(child)) {
        if (child.id === containerId) return { parent: node, index: i }
        const found = walk(child)
        if (found) return found
      }
    }
    return null
  }
  return walk(root)
}

/**
 * 根据指针位置计算插入点。
 * 1) 命中其它叶子 → 前/后半区
 * 2) 否则取最近插槽（间隙 / spacer / 首尾空白）
 */
export function resolveDropTarget(args: {
  root: FlexContainer
  placements: Map<string, RectLike>
  pointer: { x: number; y: number }
  draggedBlockId?: string | null
  mode?: DropMode
}): DropTarget | null {
  const { root, placements, pointer, draggedBlockId, mode = 'reorder' } = args

  let hitId: string | null = null
  let hitRect: RectLike | null = null
  for (const [blockId, rect] of placements) {
    if (draggedBlockId && blockId === draggedBlockId) continue
    if (
      pointer.x >= rect.x &&
      pointer.x <= rect.x + rect.w &&
      pointer.y >= rect.y &&
      pointer.y <= rect.y + rect.h
    ) {
      hitId = blockId
      hitRect = rect
      break
    }
  }
  if (hitId && hitRect) {
    const loc = findLeafParent(root, hitId)
    if (loc) {
      const vertical = loc.parent.type === 'column'
      let before = vertical
        ? pointer.y < hitRect.y + hitRect.h / 2
        : pointer.x < hitRect.x + hitRect.w / 2
      // 命中末内容下半区且锚定后是整页 EOF：改为插在该块前，线贴其上边界。
      // 真正「插到文末」走块外空白 nearestSlot（线在空位前缘）。
      // insert 例外：块下方空白正是用户想放新块的地方，不能弹回块前。
      if (!before && mode === 'reorder') {
        const peek = resolveDropAnchor(root, loc.parent, loc.index, false, mode)
        if (isDropEof(peek.parent, peek.index)) before = true
      }
      const anchor = resolveDropAnchor(root, loc.parent, loc.index, before, mode)
      const areas = solveNodeAreas(root)
      return {
        parentId: anchor.parent.id,
        index: anchor.index,
        line: dropLineAtIndex(root, anchor.parent, anchor.index, placements, areas),
      }
    }
  }

  return nearestSlotDropTarget(root, placements, pointer, mode)
}

function isDropEof(parent: FlexContainer, index: number): boolean {
  for (let i = index; i < parent.children.length; i++) {
    if (!isSpacer(parent.children[i]!)) return false
  }
  return true
}

/**
 * 将「块前/后」解析为可插入的内容前缘：
 * - 跳过 spacer，避免线落在内容下沿（spacer 顶）
 * - 若「块后」只剩 spacer 直到容器末尾，上收到父级插在该容器之后
 *
 * insert 模式不做这两件事：新块要的就是那片空白，落进 spacer 或留在原容器末尾，
 * 上收会让它变成邻列窄条。
 */
function resolveDropAnchor(
  root: FlexContainer,
  parent: FlexContainer,
  leafIndex: number,
  before: boolean,
  mode: DropMode = 'reorder',
): { parent: FlexContainer; index: number } {
  let host = parent
  let index = before ? leafIndex : leafIndex + 1

  if (mode === 'insert') {
    const spacer = spacerChildAt(host, index)
    if (spacer) return { parent: spacer, index: 0 }
  }

  index = skipSpacersIn(host, index)

  if (!before && index >= host.children.length) {
    if (mode === 'insert') return { parent: host, index }
    // 落在 wrap cell 等「内容+尾部 spacer」末尾时，改为插到父级该 cell 之后
    let outer = findContainerParent(root, host.id)
    while (outer) {
      const nextIndex = skipSpacersIn(outer.parent, outer.index + 1)
      if (nextIndex < outer.parent.children.length || outer.parent.id === root.id) {
        host = outer.parent
        index = nextIndex
        break
      }
      outer = findContainerParent(root, outer.parent.id)
    }
  }

  return { parent: host, index }
}

/** 该位置上的占位容器；插入时它就是用户看到的那片空白 */
function spacerChildAt(parent: FlexContainer, index: number): FlexContainer | null {
  const child = parent.children[index]
  if (!child || !isContainer(child) || !isSpacer(child)) return null
  return child
}

/** 插槽转落点引导线（供插入拖放与重排空白落点共用） */
export function dropTargetFromSlot(
  root: FlexContainer,
  slot: InsertSlot,
  placements: Map<string, RectLike>,
  mode: DropMode = 'reorder',
): DropTarget {
  const parent = findContainerById(root, slot.parentId)
  const areas = solveNodeAreas(root)
  if (!parent) {
    return {
      parentId: slot.parentId,
      index: slot.index,
      line:
        slot.axis === 'y'
          ? { x: slot.x, y: slot.y, w: 0.2, h: 0, axis: 'y' }
          : { x: slot.x, y: slot.y, w: 0, h: 0.2, axis: 'x' },
    }
  }
  // 与 hit 路径一致：slot.index 视为「插到此前一子之后」，走 resolveDropAnchor 上收
  const anchor =
    slot.index <= 0
      ? resolveDropAnchorAtStart(parent, mode)
      : resolveDropAnchor(root, parent, Math.max(0, slot.index - 1), false, mode)

  return {
    parentId: anchor.parent.id,
    index: anchor.index,
    line: dropLineAtIndex(root, anchor.parent, anchor.index, placements, areas),
  }
}

/** 容器首位：insert 时首个 spacer 本身就是可落的空白 */
function resolveDropAnchorAtStart(
  parent: FlexContainer,
  mode: DropMode,
): { parent: FlexContainer; index: number } {
  if (mode === 'insert') {
    const spacer = spacerChildAt(parent, 0)
    if (spacer) return { parent: spacer, index: 0 }
  }
  return { parent, index: skipSpacersIn(parent, 0) }
}

function skipSpacersIn(container: FlexContainer, from: number): number {
  let i = from
  while (i < container.children.length && isSpacer(container.children[i]!)) i++
  return i
}

/**
 * 按 drop index 画前缘线：始终优先后继内容的上/左；
 * 整页 EOF 时若末子为 spacer 用其顶缘，否则才用末内容底缘（块外空白落点）。
 */
function dropLineAtIndex(
  root: FlexContainer,
  parent: FlexContainer,
  index: number,
  placements: Map<string, RectLike>,
  areas: Map<string, RectLike>,
): DropTarget['line'] {
  const vertical = parent.type === 'column'
  const n = parent.children.length
  const parentArea = areas.get(parent.id)
  if (n === 0) {
    const fallback = parentArea ?? { x: 0, y: 0, w: 0.2, h: 0.2 }
    return vertical
      ? { x: fallback.x, y: fallback.y, w: fallback.w, h: 0, axis: 'y' }
      : { x: fallback.x, y: fallback.y, w: 0, h: fallback.h, axis: 'x' }
  }

  let host = parent
  let at = skipSpacersIn(parent, index)

  // 本容器无后继内容 → 向祖先找下一个非 spacer 兄弟的前缘
  if (at >= host.children.length || isSpacer(host.children[at]!)) {
    let outer = findContainerParent(root, host.id)
    while (outer) {
      const next = skipSpacersIn(outer.parent, outer.index + 1)
      if (next < outer.parent.children.length && !isSpacer(outer.parent.children[next]!)) {
        host = outer.parent
        at = next
        break
      }
      outer = findContainerParent(root, outer.parent.id)
    }
  }

  if (at < host.children.length && !isSpacer(host.children[at]!)) {
    const bounds =
      nodeBounds(host.children[at]!, placements, areas) ??
      parentArea ?? { x: 0, y: 0, w: 0.2, h: 0.2 }
    return vertical
      ? { x: bounds.x, y: bounds.y, w: bounds.w, h: 0, axis: 'y' }
      : { x: bounds.x, y: bounds.y, w: 0, h: bounds.h, axis: 'x' }
  }

  // 真·EOF：优先 trailing spacer 的顶/左（空位前缘），避免贴在文字底边
  const last = host.children[host.children.length - 1]!
  if (isSpacer(last)) {
    const bounds =
      nodeBounds(last, placements, areas) ??
      parentArea ?? { x: 0, y: 0, w: 0.2, h: 0.2 }
    return vertical
      ? { x: bounds.x, y: bounds.y, w: bounds.w, h: 0, axis: 'y' }
      : { x: bounds.x, y: bounds.y, w: 0, h: bounds.h, axis: 'x' }
  }
  const bounds =
    nodeBounds(last, placements, areas) ??
    parentArea ?? { x: 0, y: 0, w: 0.2, h: 0.2 }
  return vertical
    ? { x: bounds.x, y: bounds.y + bounds.h, w: bounds.w, h: 0, axis: 'y' }
    : { x: bounds.x + bounds.w, y: bounds.y, w: 0, h: bounds.h, axis: 'x' }
}

function nearestSlotDropTarget(
  root: FlexContainer,
  placements: Map<string, RectLike>,
  pointer: { x: number; y: number },
  mode: DropMode = 'reorder',
): DropTarget | null {
  const slots = collectInsertSlots(root, placements, undefined, mode)
  if (slots.length === 0) {
    // 整页只有一块时仍允许落到根首/尾
    const rootArea = solveNodeAreas(root).get(root.id)
    if (!rootArea) return null
    const before = root.type === 'column'
      ? pointer.y < rootArea.y + rootArea.h / 2
      : pointer.x < rootArea.x + rootArea.w / 2
    const index = before ? 0 : root.children.length
    const slot: InsertSlot = {
      parentId: root.id,
      index,
      x: root.type === 'column' ? rootArea.x + rootArea.w / 2 : before ? rootArea.x : rootArea.x + rootArea.w,
      y: root.type === 'column' ? (before ? rootArea.y : rootArea.y + rootArea.h) : rootArea.y + rootArea.h / 2,
      axis: root.type === 'column' ? 'y' : 'x',
    }
    return dropTargetFromSlot(root, slot, placements, mode)
  }

  let best: InsertSlot | null = null
  let bestDist = Infinity
  for (const slot of slots) {
    const dx = pointer.x - slot.x
    const dy = pointer.y - slot.y
    const dist = dx * dx + dy * dy
    if (dist < bestDist) {
      bestDist = dist
      best = slot
    }
  }
  if (!best) return null
  // 过远则不吸附，避免整页乱跳；约 25% 画布对角线
  if (bestDist > 0.25 * 0.25) return null
  return dropTargetFromSlot(root, best, placements, mode)
}
