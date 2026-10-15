import type { ElkNode } from 'elkjs/lib/elk-api'
import { flowchartStyle as style } from './diagramStyle'
import type { DiagramBlock } from './types'

type Geometry = NonNullable<DiagramBlock['geometry']>
const cache = new Map<string, Promise<Geometry>>()

function validRoutes(graph: ElkNode, block: DiagramBlock): boolean {
  const nodes = new Map(graph.children?.map(n => [n.id, n]))
  const attached = (p: { x: number; y: number }, id: string) => {
    const n = nodes.get(id)
    if (!n) return false
    const x = n.x ?? 0, y = n.y ?? 0, w = n.width ?? 0, h = n.height ?? 0
    return p.x >= x - 0.01 && p.x <= x + w + 0.01 && p.y >= y - 0.01 && p.y <= y + h + 0.01
      && Math.min(Math.abs(p.x - x), Math.abs(p.x - x - w), Math.abs(p.y - y), Math.abs(p.y - y - h)) < 0.01
  }
  return nodes.size === block.nodes.length && graph.edges?.length === block.edges.length
    && graph.edges.every((e, i) => {
      const s = e.sections?.[0], expected = block.edges[i]
      if (!s || e.sections?.length !== 1 || e.sources[0] !== expected.source || e.targets[0] !== expected.target) return false
      const points = [s.startPoint, ...(s.bendPoints ?? []), s.endPoint]
      return attached(s.startPoint, expected.source) && attached(s.endPoint, expected.target)
        && points.slice(1).every((p, k) => Math.abs(p.x - points[k].x) < 0.01 || Math.abs(p.y - points[k].y) < 0.01)
    })
}

async function compute(block: DiagramBlock, width: number, height: number, fontFamily: string): Promise<Geometry> {
  const { default: ELK } = await import('elkjs/lib/elk.bundled.js')
  const elk = new ELK()
  const ctx = document.createElement('canvas').getContext('2d')!
  const font = Math.max(10, block.style?.size_pt || style.font_size)
  const labelFont = font * style.label_font_ratio
  const wrap = (text: string, maxWidth: number, size: number) => {
    ctx.font = `${size}px ${fontFamily}`
    return text.split('\n').flatMap(paragraph => {
      const lines: string[] = []
      let current = ''
      for (const char of paragraph) {
        if (current && ctx.measureText(current + char).width > maxWidth) {
          lines.push(current)
          current = ''
        }
        current += char
      }
      return [...lines, current]
    })
  }
  const preferred = { TB: 'DOWN', LR: 'RIGHT', BT: 'UP', RL: 'LEFT' }[block.direction || 'TB']
  const candidates = style.node_widths.flatMap(nodeWidth => {
    const texts = new Map(block.nodes.map(n => [n.id, {
      title: wrap(n.title, nodeWidth - 2 * style.node_padding, font),
      desc: n.desc ? wrap(n.desc, nodeWidth - 2 * style.node_padding, font) : [],
    }]))
    const children = block.nodes.map(n => {
      const t = texts.get(n.id)!
      return { id: n.id, width: nodeWidth, height: Math.max(40, (t.title.length + t.desc.length) * font * style.line_height + 18) }
    })
    const edges = block.edges.map((e, i) => {
      const lines = wrap(e.label || '', 112, labelFont)
      return {
        id: `edge-${i}`, sources: [e.source], targets: [e.target],
        labels: e.label ? [{ text: lines.join('\n'),
          width: Math.min(112, Math.max(...lines.map(l => l.length)) * labelFont) + 2 * style.label_padding_x,
          height: lines.length * labelFont * style.line_height + 2 * style.label_padding_y,
          layoutOptions: { 'elk.edgeLabels.inline': 'true' },
        }] : [],
      }
    })
    return [[preferred, false], ['DOWN', true], ['RIGHT', true]].map(([direction, wrapLayers]) => ({
      texts,
      graph: { id: 'root', children, edges, layoutOptions: {
        ...style.layout_options,
        'elk.direction': String(direction),
        'elk.aspectRatio': String(width / Math.max(height, 1)),
        'elk.layered.wrapping.strategy': wrapLayers ? 'MULTI_EDGE' : 'OFF',
      } },
    }))
  })
  // ELK mutates graphs. Candidates must not share node/edge objects during layout.
  const graphs: ElkNode[] = await Promise.all(candidates.map(c => elk.layout(structuredClone(c.graph) as ElkNode)))
  const scaleFor = (g: ElkNode) => Math.min(width / Math.max(g.width || 1, 1), height / Math.max(g.height || 1, 1), 1)
  const scored = graphs.map((g, i) => ({ g, i, score: [
    Math.round(scaleFor(g) * 1000) / 1000,
    -[...candidates[i].texts.values()].reduce((sum, t) => sum + t.title.length + t.desc.length, 0),
    Math.min((g.width || 1) / width, 1) * Math.min((g.height || 1) / height, 1),
  ] })).filter(c => validRoutes(c.g, block)).sort((a, b) => {
    for (let k = 0; k < a.score.length; k++) if (a.score[k] !== b.score[k]) return b.score[k] - a.score[k]
    return 0
  })
  if (!scored.length) throw new Error('Diagram routes do not connect their nodes')
  const { g, i } = scored[0], scale = scaleFor(g)
  const dx = (width - (g.width || 0) * scale) / 2, dy = (height - (g.height || 0) * scale) / 2
  return {
    version: style.version, width, height, font_size: font * scale,
    nodes: g.children!.map(n => ({ id: n.id, x: dx + n.x! * scale, y: dy + n.y! * scale,
      width: n.width! * scale, height: n.height! * scale,
      title_lines: candidates[i].texts.get(n.id)!.title, desc_lines: candidates[i].texts.get(n.id)!.desc,
    })),
    edges: g.edges!.map(e => {
      const s = e.sections![0], label = e.labels?.[0]
      return { points: [s.startPoint, ...(s.bendPoints ?? []), s.endPoint].map(p => [dx + p.x * scale, dy + p.y * scale]),
        label: label?.text, label_x: dx + (label?.x || 0) * scale, label_y: dy + (label?.y || 0) * scale,
        label_width: (label?.width || 0) * scale, label_height: (label?.height || 0) * scale,
      }
    }),
  }
}

export function layoutLegacyDiagram(block: DiagramBlock, width: number, height: number, fontFamily: string): Promise<Geometry> {
  const key = JSON.stringify([block.nodes, block.edges, block.direction, block.style?.size_pt, width, height, fontFamily])
  const existing = cache.get(key)
  if (existing) return existing
  if (cache.size >= 32) cache.delete(cache.keys().next().value!)
  const pending = compute(block, width, height, fontFamily).catch(error => { cache.delete(key); throw error })
  cache.set(key, pending)
  return pending
}
