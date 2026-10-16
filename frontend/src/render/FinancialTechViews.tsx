import { type CSSProperties } from 'react'
import { boxCss, mergeTextCss } from '@/render/blockStyle'
import { cardHeaderInset, cardOuterInset } from './cardLayout'
import { EditableText } from '@/render/EditableText'
import {
  financialTechStyle as spec,
  panelGrid,
  panelHeaderBackground,
  panelHeaderHeight,
} from '@/render/financialTech'
import { pt, resolveColor } from '@/render/style'
import {
  CANVAS_HEIGHT_PT,
  CANVAS_WIDTH_PT,
  type CardsBlock,
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
  const inset = cardOuterInset(block.style)
  const grid = panelGrid(
    block.items.length,
    slot.rect.w * CANVAS_WIDTH_PT - 2 * inset,
    slot.rect.h * CANVAS_HEIGHT_PT - 2 * inset,
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
      data-card-grid
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
            data-card-header
            style={{
              position: 'relative',
              flexShrink: 0,
              minHeight: pt(headerHeight),
              boxSizing: 'border-box',
              padding: `${pt(6)} ${pt(cardHeaderInset(grid.width))}`,
              background: panelHeaderBackground(theme, index),
              clipPath: 'polygon(0 0, 94% 0, 100% 50%, 94% 100%, 0 100%, 6% 50%)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              textAlign: block.style?.align ?? 'center',
              gap: pt(spec.header_icon_gap_pt),
              minWidth: 0,
              overflow: 'hidden',
            }}
          >
            <span aria-hidden style={{ ...titleStyle, flexShrink: 0, width: pt(spec.header_icon_width_pt), fontSize: pt(12) }}>
              {item.icon ?? String(index + 1).padStart(2, '0')}
            </span>
            {field(index, 'title', { ...titleStyle, minWidth: 0, flex: 1 })}
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
