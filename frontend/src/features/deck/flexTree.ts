import {
  solveNodeAreas,
  type FlexContainer,
  type FlexLeaf,
  type FlexNode,
  type GroupPreset,
} from '@/render/flexLayout'

export const RATIO_SNAP_TOKENS = [33, 38, 50, 62, 67] as const

export type FlexBlockType = 'text' | 'bullets' | 'image' | 'chart' | 'table' | 'kpi'

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
    container.children[i]!.grow = Math.max(0.25, grows[i]!)
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

/** 双列吸附到 33/38/50/62/67；多列仅归一化到 100 */
export function snapRatios(ratios: number[]): number[] {
  const n = ratios.length
  if (n <= 0) return ratios
  if (n === 2) {
    const total = ratios[0]! + ratios[1]!
    if (total <= 0) return [50, 50]
    const pct = (ratios[0]! / total) * 100
    const pairs = RATIO_SNAP_TOKENS.flatMap((a) =>
      RATIO_SNAP_TOKENS.filter((b) => Math.abs(a + b - 100) < 1e-9).map(
        (b) => [a, b] as const,
      ),
    )
    const best = pairs.reduce((acc, pair) =>
      Math.abs(pair[0] - pct) < Math.abs(acc[0] - pct) ? pair : acc,
    )
    return [best[0], best[1]]
  }
  const sum = ratios.reduce((a, b) => a + b, 0)
  if (sum <= 0) return Array.from({ length: n }, () => 100 / n)
  return ratios.map((r) => (r / sum) * 100)
}

/** 拖动第 leftIndex|leftIndex+1 分隔线时，按归一化 x 重算整行 ratios */
export function ratiosFromDividerDrag(args: {
  ratios: number[]
  leftIndex: number
  /** 指针在行内容区的相对位置 0..1 */
  t: number
}): number[] {
  const { ratios, leftIndex, t } = args
  const n = ratios.length
  if (leftIndex < 0 || leftIndex >= n - 1) return ratios
  const clampedT = Math.max(0.05, Math.min(0.95, t))

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
  const localClamped = Math.max(0.1, Math.min(0.9, local))
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

  const clampedT = Math.max(0.05, Math.min(0.95, t))
  const topEdge = prefix / total
  const bottomEdge = (prefix + pair) / total
  const local =
    (clampedT - topEdge) / Math.max(bottomEdge - topEdge, 1e-9)
  const localClamped = Math.max(0.12, Math.min(0.88, local))
  next[topIndex] = Math.max(0.25, pair * localClamped)
  next[topIndex + 1] = Math.max(0.25, pair * (1 - localClamped))
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
 * 单子容器（常见列包装）不收集，避免空列两侧刷满 +。
 */
export function collectInsertSlots(
  root: FlexContainer,
  placements: Map<string, RectLike>,
): InsertSlot[] {
  const result: InsertSlot[] = []

  const walk = (node: FlexContainer, isRoot: boolean) => {
    const allow = isRoot || node.children.length >= 2
    if (allow) {
      const vertical = node.type === 'column'
      const childBounds = node.children.map((child) => nodeBounds(child, placements))
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

/**
 * 保证选中块在指定轴上可拉伸：必要时插入 spacer 或包一层 row。
 * 返回用于拖拽的 containerId + 分隔线左侧/上方子项 index，以及改写后的树。
 */
export function ensureResizePair(
  root: FlexContainer,
  blockId: string,
  axis: 'x' | 'y',
): { tree: FlexContainer; containerId: string; index: number } | null {
  const tree = cloneTree(root)
  const loc = findLeafParent(tree, blockId)
  if (!loc) return null

  if (axis === 'y') {
    return ensureHeightPair(tree, loc.parent, loc.index, loc.leaf)
  }
  return ensureWidthPair(tree, loc.parent, loc.index, loc.leaf)
}

function ensureHeightPair(
  tree: FlexContainer,
  parent: FlexContainer,
  index: number,
  _leaf: FlexLeaf,
): { tree: FlexContainer; containerId: string; index: number } | null {
  // 高度由 column 子项 grow 控制；若父是 row，则调 row 在其父 column 中的 grow
  let column: FlexContainer
  let unitIndex: number

  if (parent.type === 'column') {
    column = parent
    unitIndex = index
  } else {
    const outer = findContainerParent(tree, parent.id)
    if (!outer) {
      // row 即根：外包一层 column + spacer
      const oldRootChildren = [...tree.children]
      const oldRootType = tree.type
      const oldRatios = tree.ratios
      const oldGap = tree.gap_pt
      const inner: FlexContainer = {
        type: oldRootType,
        id: newNodeId('row'),
        children: oldRootChildren,
        gap_pt: oldGap,
        ratios: oldRatios,
        grow: 1,
      }
      tree.type = 'column'
      tree.ratios = null
      tree.children = [inner, makeSpacer(1)]
      // 拆分 grow
      inner.grow = 1
      return { tree, containerId: tree.id, index: 0 }
    }
    if (outer.parent.type !== 'column') return null
    column = outer.parent
    unitIndex = outer.index
  }

  const unit = column.children[unitIndex]
  if (!unit) return null

  if (unitIndex < column.children.length - 1) {
    return { tree, containerId: column.id, index: unitIndex }
  }

  // 末子：在下方加 spacer，并从当前单元拆一半 grow
  const source = unit.grow ?? 1
  const half = Math.max(source / 2, 0.25)
  unit.grow = half
  column.children.push(makeSpacer(half))
  return { tree, containerId: column.id, index: unitIndex }
}

function ensureWidthPair(
  tree: FlexContainer,
  parent: FlexContainer,
  index: number,
  leaf: FlexLeaf,
): { tree: FlexContainer; containerId: string; index: number } | null {
  if (parent.type === 'row') {
    if (index < parent.children.length - 1) {
      return { tree, containerId: parent.id, index }
    }
    const unit = parent.children[index]
    if (!unit) return null
    const ratios =
      parent.ratios?.length === parent.children.length
        ? [...parent.ratios]
        : Array.from({ length: parent.children.length }, () => 100 / parent.children.length)
    const source = ratios[index] ?? 50
    const half = Math.max(source / 2, 8)
    ratios[index] = half
    ratios.push(half)
    parent.ratios = ratios
    parent.children.push(makeSpacer(1))
    return { tree, containerId: parent.id, index }
  }

  // 父为 column：叶子通栏，包一层 row + 右侧 spacer
  const unit = parent.children[index]
  if (!unit || !isLeaf(unit) || unit.block_id !== leaf.block_id) {
    // 可能已是单列包装
    if (unit && isContainer(unit) && unit.type === 'column' && unit.children.length === 1) {
      const innerLeaf = unit.children[0]
      if (innerLeaf && isLeaf(innerLeaf) && innerLeaf.block_id === leaf.block_id) {
        const row: FlexContainer = {
          type: 'row',
          id: newNodeId('row'),
          gap_pt: 0,
          ratios: [75, 25],
          grow: unit.grow ?? 1,
          children: [unit, makeSpacer(1)],
        }
        parent.children[index] = row
        return { tree, containerId: row.id, index: 0 }
      }
    }
    // 上溯：若父列在 row 中
    const outer = findContainerParent(tree, parent.id)
    if (outer?.parent.type === 'row') {
      const row = outer.parent
      const wrapIndex = outer.index
      if (wrapIndex < row.children.length - 1) {
        return { tree, containerId: row.id, index: wrapIndex }
      }
      const ratios =
        row.ratios?.length === row.children.length
          ? [...row.ratios]
          : Array.from({ length: row.children.length }, () => 100 / row.children.length)
      const source = ratios[wrapIndex] ?? 50
      const half = Math.max(source / 2, 8)
      ratios[wrapIndex] = half
      ratios.push(half)
      row.ratios = ratios
      row.children.push(makeSpacer(1))
      return { tree, containerId: row.id, index: wrapIndex }
    }
  }

  const row: FlexContainer = {
    type: 'row',
    id: newNodeId('row'),
    gap_pt: 0,
    ratios: [75, 25],
    grow: unit?.grow ?? 1,
    children: [leaf, makeSpacer(1)],
  }
  parent.children[index] = row
  return { tree, containerId: row.id, index: 0 }
}

function findContainerParent(
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
 * 根据指针位置与目标块，计算插入点。
 * axis 取目标父容器方向：column → 上下插；row → 左右插。
 */
export function resolveDropTarget(args: {
  root: FlexContainer
  placements: Map<string, RectLike>
  pointer: { x: number; y: number }
  draggedBlockId: string
}): DropTarget | null {
  const { root, placements, pointer, draggedBlockId } = args

  let hitId: string | null = null
  let hitRect: RectLike | null = null
  for (const [blockId, rect] of placements) {
    if (blockId === draggedBlockId) continue
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
  if (!hitId || !hitRect) return null

  const loc = findLeafParent(root, hitId)
  if (!loc) return null

  const vertical = loc.parent.type === 'column'
  const before = vertical
    ? pointer.y < hitRect.y + hitRect.h / 2
    : pointer.x < hitRect.x + hitRect.w / 2

  const index = before ? loc.index : loc.index + 1
  const line = vertical
    ? {
        x: hitRect.x,
        y: before ? hitRect.y : hitRect.y + hitRect.h,
        w: hitRect.w,
        h: 0,
        axis: 'y' as const,
      }
    : {
        x: before ? hitRect.x : hitRect.x + hitRect.w,
        y: hitRect.y,
        w: 0,
        h: hitRect.h,
        axis: 'x' as const,
      }

  return { parentId: loc.parent.id, index, line }
}
