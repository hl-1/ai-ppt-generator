import type { CSSProperties } from 'react'
import { pt, resolveColor, textStyleToCss } from '@/render/style'
import type {
  Block,
  BulletsBlock,
  ChartBlock,
  ImageBlock,
  KpiBlock,
  Slot,
  TableBlock,
  TextBlock,
  Theme,
} from '@/render/types'

interface BlockProps<T> {
  block: T
  slot: Slot
  theme: Theme
}

function TextView({ block, slot, theme }: BlockProps<TextBlock>) {
  return (
    <p style={{ ...textStyleToCss(theme, slot.text_style ?? 'body'), margin: 0 }}>{block.text}</p>
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

function BulletsView({ block, slot, theme }: BlockProps<BulletsBlock>) {
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
        <li key={item} style={{ display: 'flex', alignItems: 'flex-start' }}>
          <BulletMarker theme={theme} index={index} />
          <span>{item}</span>
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
      <path d="M0 78 L34 52 L58 70 L100 40 L100 100 L0 100 Z" fill={resolveColor(theme, 'accent')} opacity="0.16" />
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

/** 原生图表在后续里程碑接入，此处先按主题呈现数据摘要，不伪造图形 */
function ChartView({ block, theme }: BlockProps<ChartBlock>) {
  const label = textStyleToCss(theme, 'chart_label')

  return (
    <div
      style={{
        ...label,
        width: '100%',
        height: '100%',
        border: `${pt(theme.shape.border_width_pt)} dashed ${resolveColor(theme, 'line_strong')}`,
        borderRadius: pt(theme.shape.radius_pt),
        display: 'flex',
        flexDirection: 'column',
        justifyContent: 'center',
        gap: pt(8),
        padding: pt(20),
      }}
    >
      <span>
        {block.chart_type} 图 · {block.categories.join(' / ')}
        {block.unit ? ` · 单位：${block.unit}` : ''}
      </span>
      {block.series.map((series, index) => (
        <span key={series.name} style={{ color: theme.palette.chart_series[index] }}>
          {series.name}：{series.values.join('、')}
        </span>
      ))}
    </div>
  )
}

function TableView({ block, theme }: BlockProps<TableBlock>) {
  const headerStyle = textStyleToCss(theme, 'table_header')
  const cellStyle = textStyleToCss(theme, 'table_cell')
  const border = `${pt(theme.shape.border_width_pt)} solid ${resolveColor(theme, 'line')}`
  const cellPadding: CSSProperties = { padding: `${pt(9)} ${pt(12)}`, textAlign: 'left' }

  return (
    <table style={{ width: '100%', borderCollapse: 'collapse', tableLayout: 'fixed' }}>
      <thead>
        <tr>
          {block.header.map((cell) => (
            <th
              key={cell}
              style={{ ...headerStyle, ...cellPadding, borderBottom: `${pt(1.5)} solid ${resolveColor(theme, 'accent')}` }}
            >
              {cell}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {block.rows.map((row, rowIndex) => (
          <tr key={row.join('|') || rowIndex}>
            {row.map((cell, cellIndex) => (
              <td key={`${cellIndex}-${cell}`} style={{ ...cellStyle, ...cellPadding, borderBottom: border }}>
                {cell}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  )
}

function KpiView({ block, theme }: BlockProps<KpiBlock>) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: pt(8) }}>
      <span style={{ ...textStyleToCss(theme, 'kpi_value'), whiteSpace: 'nowrap' }}>
        {block.value}
      </span>
      <span style={textStyleToCss(theme, 'kpi_label')}>{block.label}</span>
      {block.note && <span style={textStyleToCss(theme, 'kpi_note')}>{block.note}</span>}
    </div>
  )
}

export function BlockView({ block, slot, theme }: BlockProps<Block>) {
  switch (block.type) {
    case 'text':
      return <TextView block={block} slot={slot} theme={theme} />
    case 'bullets':
      return <BulletsView block={block} slot={slot} theme={theme} />
    case 'image':
      return <ImageView block={block} slot={slot} theme={theme} />
    case 'chart':
      return <ChartView block={block} slot={slot} theme={theme} />
    case 'table':
      return <TableView block={block} slot={slot} theme={theme} />
    case 'kpi':
      return <KpiView block={block} slot={slot} theme={theme} />
  }
}
