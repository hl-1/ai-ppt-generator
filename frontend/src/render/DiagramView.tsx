import { useEffect, useState } from 'react'
import { EditableText } from './EditableText'
import { SharedDiagramView } from './SharedDiagramView'
import { layoutLegacyDiagram } from './diagramLayout'
import { flowchartStyle, themedFlowchartStyle } from './diagramStyle'
import { pt, resolveColor, webFontStack } from './style'
import { CANVAS_HEIGHT_PT, CANVAS_WIDTH_PT, type DiagramBlock, type EditableBlockCommit, type Slot, type Theme } from './types'

type Props = { block: DiagramBlock; slot: Slot; theme: Theme; editable?: boolean
  onCommit?: (id: string, body: EditableBlockCommit) => void; onSelect?: (id: string) => void }

function FlowDiagramView({ block, slot, theme, editable, onCommit, onSelect }: Props) {
  const width = slot.rect.w * CANVAS_WIDTH_PT, height = slot.rect.h * CANVAS_HEIGHT_PT
  const fontFamily = webFontStack(theme.fonts.body)
  const saved = block.geometry?.version === flowchartStyle.version
    && Math.abs(block.geometry.width - width) < 0.5 && Math.abs(block.geometry.height - height) < 0.5
    ? block.geometry : null
  const [computed, setComputed] = useState<{ block: DiagramBlock; width: number; height: number; geometry: NonNullable<DiagramBlock['geometry']> } | null>(null)
  const [failed, setFailed] = useState(false)
  useEffect(() => {
    if (saved) return
    let cancelled = false
    setFailed(false)
    void layoutLegacyDiagram(block, width, height, fontFamily).then(geometry => {
      if (!cancelled) setComputed({ block, width, height, geometry })
    }).catch(() => { if (!cancelled) setFailed(true) })
    return () => { cancelled = true }
  }, [saved, block, width, height, fontFamily])
  const geometry = saved || (computed?.block === block && computed.width === width && computed.height === height ? computed.geometry : null)
  const colors = themedFlowchartStyle(theme)
  if (!geometry) return <div role="status" style={{ width: '100%', height: '100%', background: colors.background,
    color: colors.connector, display: 'grid', placeItems: 'center', fontSize: pt(12) }}>
    {failed ? '流程图布局失败' : ''}
  </div>
  return <SharedDiagramView block={{ ...block, geometry }} theme={theme} editable={editable} onCommit={onCommit} onSelect={onSelect} />
}

function TimelineView({ block, theme, editable, onCommit, onSelect }: Props) {
  const columns = block.nodes.length <= 3 ? block.nodes.length : block.nodes.length <= 4 ? 2 : 3
  return <div data-diagram-engine="timeline" style={{ display: 'grid', width: '100%', height: '100%',
    gridTemplateColumns: `repeat(${Math.max(1, columns * 2)},minmax(0,1fr))`, gridAutoRows: '1fr', columnGap: pt(8), rowGap: pt(16) }}>
    {block.nodes.map((node, i) => <div key={node.id} onClick={() => onSelect?.(block.id)} style={{
      position: 'relative', gridColumn: `${columns - Math.min(columns, block.nodes.length - Math.floor(i / columns) * columns) + (i % columns) * 2 + 1} / span 2`,
      minWidth: 0, minHeight: 0, padding: pt(12), display: 'flex', flexDirection: 'column', justifyContent: 'center', gap: pt(6),
      background: resolveColor(theme, node.status === 'active' ? 'accent_soft' : 'surface'),
      border: `${pt(1)} solid ${resolveColor(theme, 'line')}`, borderRadius: pt(Math.min(theme.shape.radius_pt, 8)),
      color: resolveColor(theme, 'ink'), fontFamily: webFontStack(theme.fonts.body), overflow: 'hidden',
    }}>
      {(['title', 'desc'] as const).map(field => node[field] && <div key={field} style={{
        fontSize: pt(block.style?.size_pt || (field === 'title' ? theme.text_styles.subtitle.size_pt : theme.text_styles.body.size_pt)),
        fontWeight: field === 'title' ? 600 : 400, lineHeight: 1.25, overflowWrap: 'anywhere',
      }}>{editable && onCommit ? <EditableText value={node[field]} multiline ariaLabel={`编辑阶段 ${i + 1} ${field}`}
        onCommit={value => onCommit(block.id, { type: 'diagram', diagram_type: 'timeline', mermaid: null,
          nodes: block.nodes.map(n => n.id === node.id ? { ...n, [field]: value } : n), edges: block.edges })} /> : node[field]}</div>)}
      {node.status === 'done' && <span style={{ position: 'absolute', right: pt(10), top: pt(8),
        fontSize: pt(theme.text_styles.caption.size_pt), color: resolveColor(theme, 'accent') }}>已完成</span>}
    </div>)}
  </div>
}

export function DiagramView(props: Props) {
  return props.block.diagram_type === 'timeline' ? <TimelineView {...props} /> : <FlowDiagramView {...props} />
}
