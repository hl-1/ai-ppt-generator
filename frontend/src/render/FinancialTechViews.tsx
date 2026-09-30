import { useId, type CSSProperties } from 'react'
import { boxCss, mergeTextCss } from '@/render/blockStyle'
import { EditableText } from '@/render/EditableText'
import {
  financialTechStyle as spec,
  panelGrid,
  panelHeaderBackground,
  panelHeaderHeight,
  platformConnector,
  platformNodeRects,
} from '@/render/financialTech'
import { pt, resolveColor } from '@/render/style'
import {
  CANVAS_HEIGHT_PT,
  CANVAS_WIDTH_PT,
  type CardsBlock,
  type DiagramBlock,
  type DiagramEdge,
  type EditableBlockCommit,
  type Slot,
  type Theme,
} from '@/render/types'

type Props<T> = {
  block: T
  theme: Theme
  slot: Slot
  editable?: boolean
  onCommit?: (blockId: string, body: EditableBlockCommit) => void
  onSelect?: (blockId: string) => void
}

export function FinancialCardsView({
  block,
  theme,
  slot,
  editable,
  onCommit,
  onSelect,
}: Props<CardsBlock>) {
  const grid = panelGrid(
    block.items.length,
    slot.rect.w * CANVAS_WIDTH_PT,
    slot.rect.h * CANVAS_HEIGHT_PT,
  )
  const headerHeight = panelHeaderHeight(
    grid.height,
    block.style?.size_pt ?? theme.text_styles.subtitle.size_pt,
    theme.text_styles.subtitle.line_height,
  )
  const titleStyle = mergeTextCss(theme, 'subtitle', block.style)
  const bodyStyle = mergeTextCss(theme, 'body', block.style)
  const cyan = theme.palette.chart_series[1] ?? theme.palette.accent
  const field = (index: number, name: 'title' | 'desc', style: CSSProperties) => {
    const text = block.items[index][name]
    return editable && onCommit ? (
      <EditableText
        value={text}
        ariaLabel={`编辑卡片${name === 'title' ? '标题' : '描述'} ${index + 1}`}
        multiline
        style={style}
        onFocus={() => onSelect?.(block.id)}
        onCommit={(value) => onCommit(block.id, { type: 'cards', index, field: name, text: value })}
      />
    ) : (
      <span style={{ ...style, whiteSpace: 'pre-line', overflowWrap: 'anywhere' }}>{text}</span>
    )
  }
  return (
    <div
      data-financial-panels
      style={{
        ...boxCss(theme, block.style),
        display: 'grid',
        gridTemplateColumns: `repeat(${grid.columns}, minmax(0, 1fr))`,
        gridAutoRows: 'minmax(0, 1fr)',
        gap: pt(spec.card_gap_pt),
      }}
    >
      {block.items.map((item, index) => (
        <div
          key={index}
          style={{
            position: 'relative',
            minWidth: 0,
            minHeight: 0,
            background: resolveColor(theme, 'surface'),
            borderRadius: pt(theme.shape.radius_pt),
            border: `${pt(0.75)} solid ${resolveColor(theme, 'line')}`,
            overflow: 'hidden',
            display: 'flex',
            flexDirection: 'column',
          }}
        >
          <div
            aria-hidden
            style={{
              position: 'absolute',
              top: 0,
              left: 0,
              right: 0,
              height: pt(2),
              background: index % 2 ? cyan : theme.palette.accent,
            }}
          />
          <div
            style={{
              position: 'relative',
              flexShrink: 0,
              height: pt(headerHeight),
              boxSizing: 'border-box',
              padding: `${pt(6)} ${pt(spec.header_padding_pt)}`,
              background: panelHeaderBackground(theme, index),
              clipPath: 'polygon(0 0, 94% 0, 100% 50%, 94% 100%, 0 100%, 6% 50%)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              textAlign: block.style?.align ?? 'center',
              gap: pt(6),
              minWidth: 0,
              overflow: 'hidden',
            }}
          >
            <span aria-hidden style={{ ...titleStyle, flexShrink: 0, fontSize: pt(12) }}>
              {item.icon ?? String(index + 1).padStart(2, '0')}
            </span>
            {field(index, 'title', { ...titleStyle, minWidth: 0 })}
          </div>
          <div
            style={{
              padding: pt(spec.card_padding_pt),
              flex: 1,
              minHeight: 0,
              display: 'flex',
              flexDirection: 'column',
              gap: pt(12),
              overflow: 'hidden',
            }}
          >
            <div
              aria-hidden
              style={{ width: pt(26), height: pt(2), background: cyan, flexShrink: 0 }}
            />
            {field(index, 'desc', { ...bodyStyle, minWidth: 0, whiteSpace: 'pre-line' })}
          </div>
          <div
            aria-hidden
            style={{
              flexShrink: 0,
              height: pt(4),
              background: index % 2 ? cyan : theme.palette.accent,
            }}
          />
        </div>
      ))}
    </div>
  )
}

export function FinancialDiagramView({
  block,
  theme,
  slot,
  editable,
  onCommit,
  onSelect,
  edges,
}: Props<DiagramBlock> & { edges: DiagramEdge[] }) {
  const width = slot.rect.w * CANVAS_WIDTH_PT
  const height = slot.rect.h * CANVAS_HEIGHT_PT
  const { rects, hub } = platformNodeRects(block.nodes, edges, width, height)
  const markerId = `platform-arrow-${useId().replace(/[^a-zA-Z0-9_-]/g, '')}`
  const cyan = theme.palette.chart_series[1] ?? theme.palette.accent
  const titleStyle = mergeTextCss(theme, 'subtitle', block.style)
  const bodyStyle = mergeTextCss(theme, 'body', block.style)
  return (
    <div
      data-financial-platform
      style={{ position: 'relative', width: '100%', height: '100%', overflow: 'hidden' }}
    >
      <svg
        aria-hidden
        viewBox={`0 0 ${width} ${height}`}
        preserveAspectRatio="none"
        style={{ position: 'absolute', inset: 0, width: '100%', height: '100%' }}
      >
        <defs>
          <marker id={markerId} markerWidth="7" markerHeight="7" refX="6" refY="3.5" orient="auto">
            <path d="M0 0 L7 3.5 L0 7 Z" fill={cyan} />
          </marker>
        </defs>
        {hub && (
          <ellipse
            cx={width / 2}
            cy={height / 2}
            rx={width * 0.2}
            ry={height * 0.34}
            fill="none"
            stroke={resolveColor(theme, 'line')}
            strokeWidth="1"
          />
        )}
        {edges.map((edge, index) => {
          const source = rects.get(edge.source)
          const target = rects.get(edge.target)
          if (!source || !target) return null
          const points = platformConnector(source, target)
          return (
            <g key={index}>
              <line {...points} stroke={cyan} strokeWidth="1.5" markerEnd={`url(#${markerId})`} />
              {edge.label && (
                <text
                  x={(points.x1 + points.x2) / 2}
                  y={(points.y1 + points.y2) / 2 - 5}
                  textAnchor="middle"
                  fill={theme.palette.ink_soft}
                  fontFamily={theme.fonts.body.web}
                  fontSize={11}
                  paintOrder="stroke"
                  stroke={theme.palette.background}
                  strokeWidth="4"
                >
                  {edge.label}
                </text>
              )}
            </g>
          )
        })}
      </svg>
      {block.nodes.map((node, index) => {
        const rect = rects.get(node.id)!
        const central = node.id === hub
        const fill =
          node.status === 'active' || central ? theme.palette.accent_soft : theme.palette.surface
        const border = node.status === 'risk' ? (theme.palette.chart_series[2] ?? cyan) : cyan
        const field = (name: 'title' | 'desc', style: CSSProperties) =>
          editable && onCommit ? (
            <EditableText
              value={node[name]}
              multiline
              ariaLabel={`编辑流程节点 ${index + 1} ${name === 'title' ? '标题' : '描述'}`}
              style={style}
              onFocus={() => onSelect?.(block.id)}
              onCommit={(text) =>
                onCommit(block.id, {
                  type: 'diagram',
                  diagram_type: block.diagram_type,
                  mermaid: null,
                  edges: block.edges,
                  nodes: block.nodes.map((current) =>
                    current.id === node.id ? { ...current, [name]: text } : current,
                  ),
                })
              }
            />
          ) : (
            <span style={{ ...style, whiteSpace: 'pre-line' }}>{node[name]}</span>
          )
        return (
          <div
            key={node.id}
            onClick={() => onSelect?.(block.id)}
            style={{
              position: 'absolute',
              left: `${(rect.x / width) * 100}%`,
              top: `${(rect.y / height) * 100}%`,
              width: `${(rect.w / width) * 100}%`,
              height: `${(rect.h / height) * 100}%`,
              boxSizing: 'border-box',
              padding: pt(spec.node_padding_pt),
              background: fill,
              border: `${pt(central ? 1.5 : 0.75)} solid ${border}`,
              borderRadius: pt(theme.shape.radius_pt),
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              justifyContent: 'center',
              gap: pt(6),
              textAlign: 'center',
              overflow: 'hidden',
            }}
          >
            <div
              aria-hidden
              style={{
                position: 'absolute',
                top: 0,
                left: pt(12),
                width: pt(24),
                height: pt(2),
                background: border,
              }}
            />
            {field('title', {
              ...titleStyle,
              color:
                central && !block.style?.color
                  ? resolveColor(theme, theme.text_styles.title.color)
                  : titleStyle.color,
              width: '100%',
              overflowWrap: 'anywhere',
              minHeight: 0,
            })}
            {(node.desc || editable) &&
              field('desc', {
                ...bodyStyle,
                width: '100%',
                overflowWrap: 'anywhere',
                minHeight: 0,
              })}
          </div>
        )
      })}
    </div>
  )
}
