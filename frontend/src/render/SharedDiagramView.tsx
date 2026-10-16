import { useId, useState } from 'react'
import { EditableText } from './EditableText'
import { webFontStack } from './style'
import { themedFlowchartStyle, roundedRoute } from './diagramStyle'
import type { DiagramBlock, EditableBlockCommit, Theme } from './types'

export function SharedDiagramView({ block, theme, editable, onCommit, onSelect }: {
  block: DiagramBlock
  theme: Theme
  editable?: boolean
  onCommit?: (id: string, body: EditableBlockCommit) => void
  onSelect?: (id: string) => void
}) {
  const id = useId().replace(/[^a-zA-Z0-9]/g, '')
  const style = themedFlowchartStyle(theme)
  const g = block.geometry!
  const [editing, setEditing] = useState<string | null>(null)
  const font = g.font_size
  const lineHeight = font * style.line_height
  const labelFont = font * style.label_font_ratio
  const scale = font / Math.max(10, block.style?.size_pt || style.font_size)
  return <svg data-diagram-engine="elk" viewBox={`0 0 ${g.width} ${g.height}`}
    width="100%" height="100%" role="img" aria-label="流程图"
    style={{ display: 'block', fontFamily: webFontStack(theme.fonts.body) }}
    onClick={() => onSelect?.(block.id)}>
    <defs><marker id={`elk-${id}`} markerWidth="7" markerHeight="7" refX="6" refY="3.5" orient="auto">
      <path d="M0,0 L7,3.5 L0,7" fill="none" stroke={style.connector} strokeWidth="1" />
    </marker></defs>
    <rect data-flowchart-background="true" width={g.width} height={g.height} fill={style.background} />
    {g.edges.map((edge, i) => <g key={i}>
      <path data-edge-index={i} d={roundedRoute(edge.points)}
        fill="none" stroke={style.connector} strokeWidth={style.stroke_width} strokeLinejoin="round" markerEnd={`url(#elk-${id})`} />
      {edge.label && <g>
        <rect data-condition-label="true" x={edge.label_x} y={edge.label_y} width={edge.label_width}
          height={edge.label_height} rx={edge.label_height / 2} fill={style.background} stroke={style.condition_border} strokeWidth={style.stroke_width} />
        {edge.label.split('\n').map((text, n) => <text key={n}
          x={edge.label_x + edge.label_width / 2} y={edge.label_y + style.label_padding_y * scale + labelFont * (1 + n * style.line_height)}
          textAnchor="middle" fontSize={labelFont} fontWeight={600} fill={style.text}>{text}</text>)}
      </g>}
    </g>)}
    {g.nodes.map((rect) => {
      const node = block.nodes.find(n => n.id === rect.id)!
      const lines = [...rect.title_lines, ...rect.desc_lines]
      const top = rect.y + (rect.height - lines.length * lineHeight) / 2
      return <g key={rect.id} data-node-id={rect.id}>
        <rect x={rect.x} y={rect.y} width={rect.width} height={rect.height} rx={style.radius * scale}
          fill={node.kind === 'decision' ? style.background : style.node_fill}
          stroke={node.kind === 'decision' ? style.condition_border : style.node_border} strokeWidth={style.stroke_width} strokeDasharray={node.kind === 'decision' ? '2 2' : undefined} />
        {editable && onCommit && <foreignObject x={rect.x + style.node_padding * scale} y={top}
          width={rect.width - 2 * style.node_padding * scale} height={rect.height - (top - rect.y)}
          opacity={editing === rect.id ? 1 : 0} onBlurCapture={e => {
            if (!e.currentTarget.contains(e.relatedTarget as Node | null)) setEditing(null)
          }}>
          <div style={{ fontSize: font, lineHeight: style.line_height, color: style.text, textAlign: 'center', overflowWrap: 'anywhere' }}>
            {(['title', 'desc'] as const).map(field => node[field] && <EditableText key={field}
              style={{ fontWeight: field === 'title' ? 600 : 400 }} onFocus={() => setEditing(rect.id)}
              value={node[field]} multiline ariaLabel={`编辑节点 ${node.title} ${field}`}
              onCommit={value => onCommit(block.id, { type: 'diagram', diagram_type: block.diagram_type,
                nodes: block.nodes.map(n => n.id === node.id ? { ...n, [field]: value } : n),
                edges: block.edges, mermaid: null })} />)}
          </div>
        </foreignObject>}
        {editing !== rect.id && lines.map((text, n) => <text key={n} pointerEvents="none"
          x={rect.x + rect.width / 2} y={top + font + n * lineHeight}
          textAnchor="middle" fontSize={font} fontWeight={n < rect.title_lines.length ? 600 : 400}
          fill={style.text}>{text}</text>)}
      </g>
    })}
  </svg>
}
