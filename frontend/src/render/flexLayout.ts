import { CANVAS_HEIGHT_PT, CANVAS_WIDTH_PT, type Rect } from './types'

export type GroupPreset =
  | 'solid_boxes'
  | 'outline_boxes'
  | 'side_line'
  | 'numbered_steps'
  | 'timeline'

export type FlexContainer = {
  type: 'row' | 'column'
  id: string
  children: FlexNode[]
  gap_pt?: number
  ratios?: number[] | null
  preset?: GroupPreset | null
  grow?: number
}

export type FlexLeaf = {
  type: 'block'
  id: string
  block_id: string
  grow?: number
  text_style?: string | null
}

export type FlexNode = FlexContainer | FlexLeaf

export type PlacedBlock = {
  block_id: string
  rect: Rect
  text_style?: string | null
}

export type SkinFrame = {
  container_id: string
  preset: GroupPreset
  child_index: number
  rect: Rect
}

/** 与 backend/app/domain/flex_layout.py PRESET_INSET_PT 保持一致 */
export const PRESET_INSET_PT: Record<GroupPreset, number> = {
  solid_boxes: 12.0,
  outline_boxes: 12.0,
  side_line: 16.0,
  numbered_steps: 20.0,
  timeline: 16.0,
}

const DEFAULT_GAP_PT = 16.0
const DEFAULT_GROW = 1.0

function isLeaf(node: FlexNode): node is FlexLeaf {
  return node.type === 'block'
}

/** 将 FlexContainer 树递归求解为归一化矩形列表；浮点路径对齐 Python solver。 */
export function solve(root: FlexContainer, canvas?: Rect): PlacedBlock[] {
  return solveWithFrames(root, canvas).placed
}

/** 每个节点（含空 spacer 容器）的分配矩形，供拉伸手柄使用 */
export function solveNodeAreas(
  root: FlexContainer,
  canvas?: Rect,
): Map<string, Rect> {
  const areas = new Map<string, Rect>()
  const walk = (node: FlexContainer, area: Rect) => {
    areas.set(node.id, area)
    if (!node.children.length) return
    const childAreas = splitArea(node, area)
    for (let i = 0; i < node.children.length; i++) {
      const child = node.children[i]!
      const content = applyPresetInset(node, childAreas[i]!)
      if (isLeaf(child)) {
        areas.set(child.id, content)
      } else {
        walk(child, content)
      }
    }
  }
  walk(root, canvas ?? { x: 0.0, y: 0.0, w: 1.0, h: 1.0 })
  return areas
}

export function solveWithFrames(
  root: FlexContainer,
  canvas?: Rect,
): { placed: PlacedBlock[]; frames: SkinFrame[] } {
  const area = canvas ?? { x: 0.0, y: 0.0, w: 1.0, h: 1.0 }
  const frames: SkinFrame[] = []
  const placed = solveContainer(root, area, frames)
  return { placed, frames }
}

function solveContainer(
  node: FlexContainer,
  area: Rect,
  frames: SkinFrame[],
): PlacedBlock[] {
  const children = node.children
  if (!children.length) return []

  const childAreas = splitArea(node, area)
  const placed: PlacedBlock[] = []
  for (let i = 0; i < children.length; i++) {
    const childArea = childAreas[i]!
    if (node.preset != null) {
      frames.push({
        container_id: node.id,
        preset: node.preset,
        child_index: i,
        rect: childArea,
      })
    }
    const content = applyPresetInset(node, childArea)
    placed.push(...solveNode(children[i]!, content, frames))
  }
  return placed
}

function solveNode(node: FlexNode, area: Rect, frames: SkinFrame[]): PlacedBlock[] {
  if (isLeaf(node)) {
    return [
      {
        block_id: node.block_id,
        rect: area,
        text_style: node.text_style,
      },
    ]
  }
  return solveContainer(node, area, frames)
}

function splitArea(node: FlexContainer, area: Rect): Rect[] {
  const n = node.children.length
  if (n === 0) return []

  const gapPt = node.gap_pt ?? DEFAULT_GAP_PT

  if (node.type === 'row') {
    const gapNorm = n > 1 ? ((n - 1) * gapPt) / CANVAS_WIDTH_PT : 0.0
    const weights = rowWeights(node.ratios, n)
    const totalW = Math.max(area.w - gapNorm, 0.0)
    let cursor = area.x
    const rects: Rect[] = []
    for (let index = 0; index < weights.length; index++) {
      const w = totalW * weights[index]!
      rects.push({ x: cursor, y: area.y, w: Math.max(w, 1e-9), h: area.h })
      cursor += w
      if (index < n - 1) {
        cursor += gapNorm
      }
    }
    return rects
  }

  const gapNorm = n > 1 ? ((n - 1) * gapPt) / CANVAS_HEIGHT_PT : 0.0
  const weights = columnWeights(node.children)
  const totalH = Math.max(area.h - gapNorm, 0.0)
  let cursor = area.y
  const rects: Rect[] = []
  for (let index = 0; index < weights.length; index++) {
    const h = totalH * weights[index]!
    rects.push({ x: area.x, y: cursor, w: area.w, h: Math.max(h, 1e-9) })
    cursor += h
    if (index < n - 1) {
      cursor += gapNorm
    }
  }
  return rects
}

function rowWeights(ratios: number[] | null | undefined, n: number): number[] {
  if (ratios == null || ratios.length !== n) {
    return Array.from({ length: n }, () => 1.0 / n)
  }
  const total = ratios.reduce((sum, r) => sum + r, 0)
  if (total <= 0) {
    return Array.from({ length: n }, () => 1.0 / n)
  }
  return ratios.map((r) => r / total)
}

function columnWeights(children: FlexNode[]): number[] {
  const grows = children.map((child) => child.grow ?? DEFAULT_GROW)
  const total = grows.reduce((sum, g) => sum + g, 0)
  if (total <= 0) {
    const n = children.length
    return Array.from({ length: n }, () => 1.0 / n)
  }
  return grows.map((g) => g / total)
}

function applyPresetInset(container: FlexContainer, childArea: Rect): Rect {
  if (container.preset == null) return childArea
  const insetPt = PRESET_INSET_PT[container.preset]
  const insetX = insetPt / CANVAS_WIDTH_PT
  const insetY = insetPt / CANVAS_HEIGHT_PT
  const w = childArea.w - 2 * insetX
  const h = childArea.h - 2 * insetY
  if (w <= 0 || h <= 0) return childArea
  return {
    x: childArea.x + insetX,
    y: childArea.y + insetY,
    w,
    h,
  }
}
