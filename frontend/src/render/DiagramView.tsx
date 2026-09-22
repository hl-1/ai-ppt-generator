import { useEffect, useId, useMemo, useState } from 'react'
import { EditableText } from '@/render/EditableText'
import { resolveColor, pt } from '@/render/style'
import {
  CANVAS_HEIGHT_PT,
  CANVAS_WIDTH_PT,
  type DiagramBlock,
  type DiagramEdge,
  type DiagramNode,
  type EditableBlockCommit,
  type Slot,
  type Theme,
} from '@/render/types'

type NodeRect = { x: number; y: number; w: number; h: number }

function nodeRects(block: DiagramBlock, width: number, height: number): Map<string, NodeRect> {
  const result = new Map<string, NodeRect>()
  const gap = block.diagram_type === 'timeline' ? 16 : 18
  if (block.diagram_type === 'timeline') {
    const nodeHeight = Math.max((height - gap * (block.nodes.length - 1)) / block.nodes.length, 1)
    block.nodes.forEach((node, index) => {
      result.set(node.id, {
        x: width * 0.12,
        y: index * (nodeHeight + gap),
        w: width * 0.82,
        h: nodeHeight,
      })
    })
    return result
  }

  const nodeWidth = Math.max((width - gap * (block.nodes.length - 1)) / block.nodes.length, 120)
  block.nodes.forEach((node, index) => {
    result.set(node.id, {
      x: index * (nodeWidth + gap),
      y: height * 0.18,
      w: nodeWidth,
      h: height * 0.64,
    })
  })
  return result
}

function connectorPoints(source: NodeRect, target: NodeRect) {
  if (target.x >= source.x + source.w) {
    return {
      x1: source.x + source.w,
      y1: source.y + source.h / 2,
      x2: target.x,
      y2: target.y + target.h / 2,
    }
  }
  return {
    x1: source.x + source.w / 2,
    y1: source.y + source.h,
    x2: target.x + target.w / 2,
    y2: target.y,
  }
}

function nodeFill(theme: Theme, status: DiagramNode['status']) {
  if (status === 'active') return resolveColor(theme, 'accent_soft')
  if (status === 'risk') return `color-mix(in srgb, ${resolveColor(theme, 'accent')} 16%, ${resolveColor(theme, 'background')})`
  return resolveColor(theme, 'surface')
}

function generatedMermaid(block: DiagramBlock): string {
  const direction = 'TB'
  const ids = new Map<string, string>()
  const safe = (value: string) =>
    value
      .replace(/[^a-zA-Z0-9_]/g, '_')
      .replace(/^_+|_+$/g, '') || 'node'
  const label = (title: string, desc: string) =>
    [title, desc]
      .filter(Boolean)
      .map((value) => value.replace(/["|]/g, "'").replace(/\s+/g, ' ').trim())
      .join('<br/>')

  const lines = [`flowchart ${direction}`]
  block.nodes.forEach((node, index) => {
    const id = `node_${safe(node.id)}_${index + 1}`
    ids.set(node.id, id)
    lines.push(`    ${id}["${label(node.title, node.desc)}"]`)
  })
  block.edges.forEach((edge) => {
    const source = ids.get(edge.source)
    const target = ids.get(edge.target)
    if (!source || !target) return
    const edgeLabel = edge.label?.replace(/[|]/g, '/').replace(/\s+/g, ' ').trim()
    lines.push(edgeLabel ? `    ${source} -->|${edgeLabel}| ${target}` : `    ${source} --> ${target}`)
  })
  return lines.join('\n')
}

function responsiveMermaidSvg(svg: string): string {
  return svg.replace(/<svg\b([^>]*)>/i, (_match, attrs: string) => {
    const cleaned = attrs
      .replace(/\sstyle="[^"]*"/i, '')
      .replace(/\swidth="[^"]*"/i, '')
      .replace(/\sheight="[^"]*"/i, '')
      .replace(/\spreserveAspectRatio="[^"]*"/i, '')
    return `<svg${cleaned} width="100%" height="100%" preserveAspectRatio="xMidYMid meet" style="display:block;width:100%;height:100%;max-width:none;">`
  })
}

function commitNodes(
  block: DiagramBlock,
  nodes: DiagramNode[],
  onCommit?: (blockId: string, body: EditableBlockCommit) => void,
) {
  onCommit?.(block.id, {
    type: 'diagram',
    diagram_type: block.diagram_type,
    mermaid: null,
    nodes,
    edges: block.edges,
  })
}

export function DiagramView({
  block,
  slot,
  theme,
  editable,
  onCommit,
  onSelect,
}: {
  block: DiagramBlock
  slot: Slot
  theme: Theme
  editable?: boolean
  onCommit?: (blockId: string, body: EditableBlockCommit) => void
  onSelect?: (blockId: string) => void
}) {
  const width = slot.rect.w * CANVAS_WIDTH_PT
  const height = slot.rect.h * CANVAS_HEIGHT_PT
  const reactId = useId()
  const mermaidId = `mermaid-${reactId.replace(/[^a-zA-Z0-9_-]/g, '')}`
  const [mermaidSvg, setMermaidSvg] = useState<string | null>(null)
  const [mermaidError, setMermaidError] = useState(false)
  const mermaidSource = block.mermaid?.trim() || generatedMermaid(block)
  const rects = useMemo(() => nodeRects(block, width, height), [block, width, height])
  const byId = new Map(block.nodes.map((node) => [node.id, node]))

  useEffect(() => {
    let cancelled = false
    setMermaidSvg(null)
    setMermaidError(false)
    void import('mermaid')
      .then(({ default: mermaid }) => {
        mermaid.initialize({
          startOnLoad: false,
          securityLevel: 'strict',
          theme: 'base',
          flowchart: { htmlLabels: true, useMaxWidth: true, curve: 'basis' },
          themeVariables: {
            primaryColor: resolveColor(theme, 'accent_soft'),
            primaryBorderColor: resolveColor(theme, 'accent'),
            primaryTextColor: resolveColor(theme, 'ink'),
            lineColor: resolveColor(theme, 'accent'),
            secondaryColor: resolveColor(theme, 'surface'),
            tertiaryColor: resolveColor(theme, 'background'),
            fontFamily: theme.fonts.body.web,
          },
        })
        return mermaid.render(mermaidId, mermaidSource)
      })
      .then(({ svg }) => {
        if (!cancelled) setMermaidSvg(responsiveMermaidSvg(svg))
      })
      .catch(() => {
        if (!cancelled) setMermaidError(true)
      })

    return () => {
      cancelled = true
      document.getElementById(mermaidId)?.remove()
    }
  }, [mermaidId, mermaidSource, theme])

  if (!mermaidError) {
    return (
      <div
        className="mermaid-diagram"
        role="img"
        aria-label="Mermaid 流程图"
        onClick={() => onSelect?.(block.id)}
        style={{
          width: '100%',
          height: '100%',
          minWidth: 0,
          minHeight: 0,
          overflow: 'hidden',
        }}
        dangerouslySetInnerHTML={mermaidSvg ? { __html: mermaidSvg } : undefined}
      />
    )
  }

  return (
    <div
      style={{
        position: 'relative',
        width: '100%',
        height: '100%',
        minWidth: 0,
        minHeight: 0,
        overflow: 'hidden',
      }}
    >
      <svg
        viewBox={`0 0 ${width} ${height}`}
        preserveAspectRatio="none"
        aria-hidden
        style={{ position: 'absolute', inset: 0, width: '100%', height: '100%' }}
      >
        <defs>
          <marker
            id={`arrow-${block.id}`}
            markerWidth="8"
            markerHeight="8"
            refX="7"
            refY="4"
            orient="auto"
            markerUnits="strokeWidth"
          >
            <path d="M0,0 L8,4 L0,8 z" fill={resolveColor(theme, 'accent')} />
          </marker>
        </defs>
        {block.edges.map((edge: DiagramEdge) => {
          const source = rects.get(edge.source)
          const target = rects.get(edge.target)
          if (!source || !target) return null
          const points = connectorPoints(source, target)
          return (
            <line
              key={`${edge.source}-${edge.target}`}
              {...points}
              stroke={resolveColor(theme, 'accent')}
              strokeWidth="2"
              markerEnd={`url(#arrow-${block.id})`}
            />
          )
        })}
      </svg>

      {block.nodes.map((node, index) => {
        const rect = rects.get(node.id)
        if (!rect) return null
        const nodeIndex = block.nodes.findIndex((item) => item.id === node.id)
        const updateNode = (field: 'title' | 'desc', value: string) => {
          const nodes = block.nodes.map((item, current) =>
            current === nodeIndex ? { ...item, [field]: value } : item,
          )
          commitNodes(block, nodes, onCommit)
        }
        return (
          <div
            key={node.id}
            style={{
              position: 'absolute',
              left: `${(rect.x / width) * 100}%`,
              top: `${(rect.y / height) * 100}%`,
              width: `${(rect.w / width) * 100}%`,
              height: `${(rect.h / height) * 100}%`,
              boxSizing: 'border-box',
              padding: pt(12),
              display: 'flex',
              flexDirection: 'column',
              gap: pt(6),
              justifyContent: 'center',
              minWidth: 0,
              overflow: 'hidden',
              color: resolveColor(theme, 'ink'),
              background: nodeFill(theme, node.status),
              border: `${pt(1)} solid ${resolveColor(theme, 'line')}`,
              borderRadius: pt(theme.shape.radius_pt),
            }}
            onClick={() => onSelect?.(block.id)}
          >
            <span
              style={{
                fontSize: pt(theme.text_styles.subtitle.size_pt),
                fontFamily: theme.fonts.body.web,
                fontWeight: theme.text_styles.subtitle.weight,
                lineHeight: theme.text_styles.subtitle.line_height,
                overflowWrap: 'break-word',
                minHeight: 0,
                overflow: 'hidden',
                flexShrink: 1,
              }}
            >
              {editable && onCommit ? (
                <EditableText
                  value={node.title}
                  ariaLabel={`编辑流程节点 ${index + 1} 标题`}
                  style={{ fontSize: pt(theme.text_styles.subtitle.size_pt), fontWeight: theme.text_styles.subtitle.weight }}
                  onFocus={() => onSelect?.(block.id)}
                  onCommit={(value) => updateNode('title', value)}
                />
              ) : (
                node.title
              )}
            </span>
            {node.desc ? (
              <span
                style={{
                  fontSize: pt(theme.text_styles.body.size_pt),
                  fontFamily: theme.fonts.body.web,
                  lineHeight: theme.text_styles.body.line_height,
                  color: resolveColor(theme, 'ink_soft'),
                  overflowWrap: 'break-word',
                  minHeight: 0,
                  overflow: 'hidden',
                  flexShrink: 1,
                }}
              >
                {editable && onCommit ? (
                  <EditableText
                    value={node.desc}
                    ariaLabel={`编辑流程节点 ${index + 1} 描述`}
                    multiline
                    style={{ fontSize: pt(theme.text_styles.body.size_pt) }}
                    onFocus={() => onSelect?.(block.id)}
                    onCommit={(value) => updateNode('desc', value)}
                  />
                ) : (
                  node.desc
                )}
              </span>
            ) : null}
            {block.diagram_type === 'timeline' && byId.get(node.id)?.status === 'done' ? (
              <span
                style={{
                  position: 'absolute',
                  right: pt(10),
                  top: pt(8),
                  fontSize: pt(theme.text_styles.caption.size_pt),
                  color: resolveColor(theme, 'accent'),
                }}
              >
                已完成
              </span>
            ) : null}
          </div>
        )
      })}
    </div>
  )
}
