import spec from '../../../shared/financial-tech-style.json'
import { mixHex } from '@/render/ambient'
import { flowLevels } from '@/render/diagramTopology'
import type { DiagramEdge, DiagramNode, Theme } from '@/render/types'

export { spec as financialTechStyle }
export const isFinancialTech = (theme: Theme) => theme.visual_style === 'financial-tech'

export function panelHeaderBackground(theme: Theme, index: number) {
  const base = index % 2
    ? mixHex(theme.palette.accent, theme.palette.accent_soft, spec.secondary_header_accent_mix)
    : theme.palette.accent
  const highlight = mixHex(
    theme.palette.chart_series[1] ?? theme.palette.accent,
    base,
    spec.header_highlight_mix,
  )
  const shade = mixHex(theme.palette.background, base, spec.header_shade_mix)
  return `linear-gradient(180deg, ${highlight}, ${shade})`
}

export function panelGrid(count: number, width: number, height: number) {
  const gap = spec.card_gap_pt
  const columns = Math.min(
    count,
    spec.card_max_columns,
    Math.max(1, Math.floor((width + gap) / (spec.card_min_width_pt + gap))),
  )
  const rows = Math.ceil(count / columns)
  return {
    columns,
    width: Math.max(1, (width - gap * (columns - 1)) / columns),
    height: Math.max(1, (height - gap * (rows - 1)) / rows),
  }
}

export function panelHeaderHeight(height: number, size: number, lineHeight: number) {
  return Math.min(height * 0.45, Math.max(spec.header_min_height_pt, size * lineHeight * 2 + 12))
}

export type PlatformRect = { x: number; y: number; w: number; h: number }

export function platformNodeRects(
  nodes: DiagramNode[],
  edges: DiagramEdge[],
  width: number,
  height: number,
) {
  const gap = spec.node_gap_pt
  const ids = new Set(nodes.map((node) => node.id))
  const valid = edges.filter(
    (edge) => ids.has(edge.source) && ids.has(edge.target) && edge.source !== edge.target,
  )
  const links = new Map(nodes.map((node) => [node.id, new Set<string>()]))
  for (const edge of valid) {
    links.get(edge.source)!.add(edge.target)
    links.get(edge.target)!.add(edge.source)
  }
  let hub =
    nodes.find(
      (node) =>
        nodes.length >= 4 &&
        links.get(node.id)!.size === nodes.length - 1 &&
        valid.every((edge) => edge.source === node.id || edge.target === node.id),
    )?.id ?? null
  const rects = new Map<string, PlatformRect>()
  if (hub && nodes.length <= 7 && width >= 380 && height >= 240) {
    const side = nodes.filter((node) => node.id !== hub)
    const rows = Math.ceil(side.length / 2)
    const nodeWidth = width * 0.26
    const nodeHeight = Math.min(88, (height - gap * (rows - 1)) / rows)
    rects.set(hub, {
      x: width * 0.355,
      y: (height - nodeHeight * 1.25) / 2,
      w: width * 0.29,
      h: nodeHeight * 1.25,
    })
    side.forEach((node, index) => {
      const y =
        (height - (rows * nodeHeight + (rows - 1) * gap)) / 2 +
        Math.floor(index / 2) * (nodeHeight + gap)
      rects.set(node.id, {
        x: index % 2 === 0 ? 0 : width - nodeWidth,
        y,
        w: nodeWidth,
        h: nodeHeight,
      })
    })
  } else {
    hub = null
    let levels = flowLevels(nodes, valid)
    // flowLevels supplies fallback zeroes, so detect cyclic components with Kahn's algorithm.
    const incoming = new Map(nodes.map((node) => [node.id, 0]))
    for (const edge of valid) incoming.set(edge.target, incoming.get(edge.target)! + 1)
    const queue = nodes.filter((node) => incoming.get(node.id) === 0).map((node) => node.id)
    for (let index = 0; index < queue.length; index++) {
      for (const edge of valid.filter((edge) => edge.source === queue[index])) {
        incoming.set(edge.target, incoming.get(edge.target)! - 1)
        if (incoming.get(edge.target) === 0) queue.push(edge.target)
      }
    }
    if (queue.length !== nodes.length)
      levels = new Map(nodes.map((node, index) => [node.id, Math.floor(index / 3)]))
    const groups = new Map<number, DiagramNode[]>()
    for (const node of nodes) {
      const level = levels.get(node.id) ?? 0
      groups.set(level, [...(groups.get(level) ?? []), node])
    }
    const rows = [...groups.entries()]
      .sort(([a], [b]) => a - b)
      .flatMap(([, group]) =>
        Array.from({ length: Math.ceil(group.length / 4) }, (_, index) =>
          group.slice(index * 4, index * 4 + 4),
        ),
      )
    const rowGap = Math.min(gap, height / (rows.length * 2))
    const rowHeight = Math.max(0.001, (height - rowGap * (rows.length - 1)) / rows.length)
    rows.forEach((row, rowIndex) => {
      const columnGap = Math.min(gap, width / (row.length * 2))
      const nodeWidth = Math.max(0.001, (width - columnGap * (row.length - 1)) / row.length)
      row.forEach((node, column) =>
        rects.set(node.id, {
          x: column * (nodeWidth + columnGap),
          y: rowIndex * (rowHeight + rowGap),
          w: nodeWidth,
          h: rowHeight,
        }),
      )
    })
  }
  return { rects, hub }
}

export function platformConnector(source: PlatformRect, target: PlatformRect) {
  const dx = target.x + target.w / 2 - source.x - source.w / 2
  const dy = target.y + target.h / 2 - source.y - source.h / 2
  const sourceScale = 0.5 / Math.max(Math.abs(dx) / source.w, Math.abs(dy) / source.h, 0.001)
  const targetScale = 0.5 / Math.max(Math.abs(dx) / target.w, Math.abs(dy) / target.h, 0.001)
  return {
    x1: source.x + source.w / 2 + dx * sourceScale,
    y1: source.y + source.h / 2 + dy * sourceScale,
    x2: target.x + target.w / 2 - dx * targetScale,
    y2: target.y + target.h / 2 - dy * targetScale,
  }
}
