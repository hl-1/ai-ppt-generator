import type { CSSProperties } from 'react'
import { ChartView } from '@/render/ChartView'
import { EditableText } from '@/render/EditableText'
import { pt, resolveColor, textStyleToCss } from '@/render/style'
import type {
  Block,
  BulletsBlock,
  EditableBlockCommit,
  ImageBlock,
  KpiBlock,
  Slot,
  TableBlock,
  TextBlock,
  TextStyleName,
  Theme,
} from '@/render/types'

/** 标题类与单元格按单行约束；正文允许换行 */
const MULTILINE_STYLES = new Set<TextStyleName>(['body', 'bullet'])

interface BlockProps<T> {
  block: T
  slot: Slot
  theme: Theme
  editable?: boolean
  onCommit?: (blockId: string, body: EditableBlockCommit) => void
}

function TextView({ block, slot, theme, editable, onCommit }: BlockProps<TextBlock>) {
  const styleName = slot.text_style ?? 'body'
  const style = textStyleToCss(theme, styleName)

  if (!editable || !onCommit) {
    return <p style={{ ...style, margin: 0 }}>{block.text}</p>
  }

  return (
    <p style={{ ...style, margin: 0 }}>
      <EditableText
        value={block.text}
        ariaLabel="编辑文字"
        multiline={MULTILINE_STYLES.has(styleName)}
        style={style}
        onCommit={(text) => onCommit(block.id, { type: 'text', text })}
      />
    </p>
  )
}

function BulletMarker({ theme, index }: { theme: Theme; index: number }) {
  const accent = resolveColor(theme, 'accent')

  if (theme.shape.bullet_marker === 'index') {
    return (
      <span
        style={{
          color: accent,
          flexShrink: 0,
          width: pt(22),
          fontVariantNumeric: 'tabular-nums',
        }}
      >
        {String(index + 1).padStart(2, '0')}
      </span>
    )
  }

  if (theme.shape.bullet_marker === 'dot') {
    return (
      <span
        style={{
          flexShrink: 0,
          width: pt(6),
          height: pt(6),
          marginRight: pt(14),
          marginTop: pt(9),
          borderRadius: '50%',
          background: accent,
        }}
      />
    )
  }

  return (
    <span
      style={{
        flexShrink: 0,
        width: pt(14),
        height: pt(1.5),
        marginRight: pt(14),
        marginTop: pt(11),
        background: accent,
      }}
    />
  )
}

function BulletsView({ block, slot, theme, editable, onCommit }: BlockProps<BulletsBlock>) {
  const textStyle = textStyleToCss(theme, slot.text_style ?? 'bullet')

  return (
    <ul
      style={{
        ...textStyle,
        listStyle: 'none',
        margin: 0,
        padding: 0,
        display: 'flex',
        flexDirection: 'column',
        gap: pt(12),
      }}
    >
      {block.items.map((item, index) => (
        <li key={`${block.id}-${index}`} style={{ display: 'flex', alignItems: 'flex-start' }}>
          <BulletMarker theme={theme} index={index} />
          {editable && onCommit ? (
            <EditableText
              value={item}
              ariaLabel={`编辑要点 ${index + 1}`}
              style={{ ...textStyle, flex: 1 }}
              onCommit={(text) => onCommit(block.id, { type: 'bullets', index, text })}
            />
          ) : (
            <span>{item}</span>
          )}
        </li>
      ))}
    </ul>
  )
}

/** 图源缺失时的降级图形，按主题色绘制，不依赖网络 */
function ImagePlaceholder({ theme, alt }: { theme: Theme; alt: string }) {
  return (
    <svg
      viewBox="0 0 100 100"
      preserveAspectRatio="none"
      role="img"
      aria-label={alt}
      style={{ width: '100%', height: '100%', display: 'block' }}
    >
      <rect width="100" height="100" fill={resolveColor(theme, 'accent_soft')} />
      <circle cx="74" cy="28" r="30" fill={resolveColor(theme, 'accent')} opacity="0.22" />
      <circle cx="74" cy="28" r="18" fill={resolveColor(theme, 'accent')} opacity="0.3" />
      <path
        d="M0 78 L34 52 L58 70 L100 40 L100 100 L0 100 Z"
        fill={resolveColor(theme, 'accent')}
        opacity="0.16"
      />
      <rect x="8" y="86" width="18" height="1.2" fill={resolveColor(theme, 'accent')} />
    </svg>
  )
}

function ImageView({ block, theme }: BlockProps<ImageBlock>) {
  if (!block.url) {
    return <ImagePlaceholder theme={theme} alt={block.alt} />
  }
  return (
    <img
      src={block.url}
      alt={block.alt}
      style={{ width: '100%', height: '100%', objectFit: 'cover', display: 'block' }}
    />
  )
}

function TableView({ block, theme, editable, onCommit }: BlockProps<TableBlock>) {
  const headerStyle = textStyleToCss(theme, 'table_header')
  const cellStyle = textStyleToCss(theme, 'table_cell')
  const border = `${pt(theme.shape.border_width_pt)} solid ${resolveColor(theme, 'line')}`
  const cellPadding: CSSProperties = { padding: `${pt(9)} ${pt(12)}`, textAlign: 'left' }

  return (
    <table style={{ width: '100%', borderCollapse: 'collapse', tableLayout: 'fixed' }}>
      <thead>
        <tr>
          {block.header.map((cell, index) => (
            <th
              key={`h-${index}`}
              style={{
                ...headerStyle,
                ...cellPadding,
                borderBottom: `${pt(1.5)} solid ${resolveColor(theme, 'accent')}`,
              }}
            >
              {editable && onCommit ? (
                <EditableText
                  value={cell}
                  ariaLabel={`编辑表头 ${index + 1}`}
                  style={headerStyle}
                  onCommit={(text) =>
                    onCommit(block.id, { type: 'table', kind: 'header', index, text })
                  }
                />
              ) : (
                cell
              )}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {block.rows.map((row, rowIndex) => (
          <tr key={`r-${rowIndex}`}>
            {row.map((cell, cellIndex) => (
              <td
                key={`c-${rowIndex}-${cellIndex}`}
                style={{ ...cellStyle, ...cellPadding, borderBottom: border }}
              >
                {editable && onCommit ? (
                  <EditableText
                    value={cell}
                    ariaLabel={`编辑单元格 ${rowIndex + 1}-${cellIndex + 1}`}
                    style={cellStyle}
                    onCommit={(text) =>
                      onCommit(block.id, {
                        type: 'table',
                        kind: 'cell',
                        row: rowIndex,
                        col: cellIndex,
                        text,
                      })
                    }
                  />
                ) : (
                  cell
                )}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  )
}

function KpiView({ block, theme, editable, onCommit }: BlockProps<KpiBlock>) {
  const valueStyle = textStyleToCss(theme, 'kpi_value')
  const labelStyle = textStyleToCss(theme, 'kpi_label')
  const noteStyle = textStyleToCss(theme, 'kpi_note')

  if (!editable || !onCommit) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: pt(8) }}>
        <span style={{ ...valueStyle, whiteSpace: 'nowrap' }}>{block.value}</span>
        <span style={labelStyle}>{block.label}</span>
        {block.note && <span style={noteStyle}>{block.note}</span>}
      </div>
    )
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: pt(8) }}>
      <EditableText
        value={block.value}
        ariaLabel="编辑指标数值"
        style={{ ...valueStyle, whiteSpace: 'nowrap' }}
        onCommit={(text) => onCommit(block.id, { type: 'kpi', field: 'value', text })}
      />
      <EditableText
        value={block.label}
        ariaLabel="编辑指标标签"
        style={labelStyle}
        onCommit={(text) => onCommit(block.id, { type: 'kpi', field: 'label', text })}
      />
      <EditableText
        value={block.note ?? ''}
        ariaLabel="编辑指标备注"
        style={noteStyle}
        onCommit={(text) => onCommit(block.id, { type: 'kpi', field: 'note', text })}
      />
    </div>
  )
}

export function BlockView({ block, slot, theme, editable, onCommit }: BlockProps<Block>) {
  switch (block.type) {
    case 'text':
      return (
        <TextView
          block={block}
          slot={slot}
          theme={theme}
          editable={editable}
          onCommit={onCommit}
        />
      )
    case 'bullets':
      return (
        <BulletsView
          block={block}
          slot={slot}
          theme={theme}
          editable={editable}
          onCommit={onCommit}
        />
      )
    case 'image':
      return <ImageView block={block} slot={slot} theme={theme} />
    case 'chart':
      return <ChartView block={block} slot={slot} theme={theme} />
    case 'table':
      return (
        <TableView
          block={block}
          slot={slot}
          theme={theme}
          editable={editable}
          onCommit={onCommit}
        />
      )
    case 'kpi':
      return (
        <KpiView
          block={block}
          slot={slot}
          theme={theme}
          editable={editable}
          onCommit={onCommit}
        />
      )
  }
}
