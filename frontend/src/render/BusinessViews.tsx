import type { CSSProperties } from 'react'
import { mergeTextCss } from '@/render/blockStyle'
import { pt, resolveColor, webFontStack } from '@/render/style'
import { CANVAS_HEIGHT_PT, CANVAS_WIDTH_PT } from '@/render/types'
import type {
  ComboChartBlock,
  FinancialTableBlock,
  Slot,
  Theme,
  WaterfallBlock,
} from '@/render/types'

function numberLabel(value: number) {
  if (Math.abs(value) >= 100) return value.toLocaleString(undefined, { maximumFractionDigits: 0 })
  if (Math.abs(value) >= 10) return value.toLocaleString(undefined, { maximumFractionDigits: 1 })
  return value.toLocaleString(undefined, { maximumFractionDigits: 2 })
}

function font(theme: Theme) {
  return webFontStack(theme.fonts.body)
}

function chartBoxWidth(slot: Slot) {
  const widthPt = Math.max(slot.rect.w * CANVAS_WIDTH_PT, 1)
  const heightPt = Math.max(slot.rect.h * CANVAS_HEIGHT_PT, 1)
  return Math.max(100, (widthPt / heightPt) * 100)
}

export function FinancialTableView({
  block,
  theme,
}: {
  block: FinancialTableBlock
  slot: Slot
  theme: Theme
}) {
  const headerStyle = mergeTextCss(theme, 'table_header', block.style)
  const cellStyle = mergeTextCss(theme, 'table_cell', block.style)
  const accent = resolveColor(theme, 'accent')
  const accentSoft = resolveColor(theme, 'accent_soft')
  const line = resolveColor(theme, 'line')
  const background = resolveColor(theme, 'background')
  const highlights = new Set((block.highlight_columns ?? []).map((index) => index + 1))
  const cell: CSSProperties = {
    padding: `${pt(7)} ${pt(12)}`,
    borderBottom: `${pt(0.75)} solid ${line}`,
    overflow: 'hidden',
    textOverflow: 'ellipsis',
  }

  return (
    <div style={{ width: '100%', height: '100%', overflow: 'hidden' }}>
      <table
        style={{
          width: '100%',
          height: '100%',
          tableLayout: 'fixed',
          borderCollapse: 'collapse',
          borderBottom: `${pt(2.5)} solid ${accent}`,
        }}
      >
        <thead>
          <tr>
            <th style={{ ...headerStyle, ...cell, width: '52%', color: '#fff', background: accent, textAlign: 'left' }}>
              {block.unit ?? ''}
            </th>
            {block.columns.map((column) => (
              <th
                key={column}
                style={{ ...headerStyle, ...cell, color: '#fff', background: accent, textAlign: 'right' }}
              >
                {column}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {block.rows.map((row, rowIndex) => (
            <tr key={`${row.label}-${rowIndex}`}>
              <td
                style={{
                  ...cellStyle,
                  ...cell,
                  background: row.spacer
                    ? `color-mix(in srgb, ${resolveColor(theme, 'surface')} 60%, ${background})`
                    : background,
                  fontWeight: row.emphasis ? 700 : cellStyle.fontWeight,
                  textAlign: 'left',
                }}
              >
                {row.label}
              </td>
              {block.columns.map((_column, valueIndex) => {
                const col = valueIndex + 1
                return (
                  <td
                    key={`${row.label}-${valueIndex}`}
                    style={{
                      ...cellStyle,
                      ...cell,
                      background: highlights.has(col) ? accentSoft : background,
                      fontWeight: row.emphasis ? 700 : cellStyle.fontWeight,
                      textAlign: 'right',
                      fontVariantNumeric: 'tabular-nums',
                    }}
                  >
                    {row.values[valueIndex] ?? ''}
                  </td>
                )
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export function WaterfallView({
  block,
  slot,
  theme,
}: {
  block: WaterfallBlock
  slot: Slot
  theme: Theme
}) {
  const items = block.items ?? []
  const values: Array<{ start: number; end: number; delta: number }> = []
  let running = 0
  for (const item of items) {
    const kind = item.kind ?? 'increase'
    if (kind === 'start' || kind === 'total') {
      values.push({ start: 0, end: item.value, delta: item.value })
      running = item.value
    } else {
      const end = running + item.value
      values.push({ start: running, end, delta: item.value })
      running = end
    }
  }
  const min = Math.min(0, ...values.map((item) => Math.min(item.start, item.end)))
  const max = Math.max(1, ...values.map((item) => Math.max(item.start, item.end)))
  const span = max - min || 1
  const y = (value: number) => 78 - ((value - min) / span) * 56
  const colors = theme.palette.chart_series
  const accent = resolveColor(theme, 'accent')
  const positive = colors[1] ?? accent
  const negative = colors[3] ?? resolveColor(theme, 'line_strong')
  const line = resolveColor(theme, 'line_strong')
  const text = resolveColor(theme, 'ink')
  const muted = resolveColor(theme, 'ink_muted')
  const boxW = chartBoxWidth(slot)
  const plotLeft = 4
  const plotRight = boxW - 4
  const plotW = plotRight - plotLeft
  const step = plotW / Math.max(items.length, 1)
  const barW = step * 0.58

  return (
    <svg viewBox={`0 0 ${boxW} 100`} width="100%" height="100%" role="img" aria-label="瀑布图">
      <line x1={plotLeft} x2={plotRight} y1={y(0)} y2={y(0)} stroke={line} strokeWidth="0.35" />
      {block.unit && (
        <text x="4" y="8" fontFamily={font(theme)} fontSize="3.2" fill={muted}>
          {block.unit}
        </text>
      )}
      {items.map((item, index) => {
        const kind = item.kind ?? 'increase'
        const entry = values[index]
        const x = plotLeft + step * index + (step - barW) / 2
        const top = Math.min(y(entry.start), y(entry.end))
        const height = Math.max(Math.abs(y(entry.start) - y(entry.end)), 1.1)
        const fill = kind === 'start' || kind === 'total' ? accent : entry.delta >= 0 ? positive : negative
        const next = values[index + 1]
        const connectorY = y(entry.end)
        const nextX = plotLeft + step * (index + 1) + (step - barW) / 2
        return (
          <g key={`${item.label}-${index}`}>
            <rect x={x} y={top} width={barW} height={height} fill={fill} />
            {next && (
              <line
                x1={x + barW}
                x2={nextX}
                y1={connectorY}
                y2={connectorY}
                stroke={line}
                strokeWidth="0.25"
                strokeDasharray="1 1"
              />
            )}
            <text
              x={x + barW / 2}
              y={Math.max(top - 2, 6)}
              textAnchor="middle"
              fontFamily={font(theme)}
              fontSize="3.4"
              fontWeight="700"
              fill={text}
            >
              {numberLabel(kind === 'start' || kind === 'total' ? item.value : entry.delta)}
            </text>
            <text x={x + barW / 2} y="88" textAnchor="middle" fontFamily={font(theme)} fontSize="3.1" fill={text}>
              {item.label}
            </text>
          </g>
        )
      })}
      {(block.callouts ?? []).slice(0, 3).map((callout, index) => {
        const anchor = Math.max(0, Math.min(items.length - 1, callout.item_index))
        const x = Math.min(boxW - 28, Math.max(8, plotLeft + step * anchor - 5))
        const yPos = 12 + index * 14
        return (
          <g key={`${callout.item_index}-${index}`}>
            <rect x={x} y={yPos} width="22" height="11" fill={resolveColor(theme, 'surface')} opacity="0.92" />
            <text x={x + 1.4} y={yPos + 3.5} fontFamily={font(theme)} fontSize="2.7" fontWeight="700" fill={text}>
              {callout.title}
            </text>
            {(callout.lines ?? []).slice(0, 2).map((lineText, lineIndex) => (
              <text
                key={lineText}
                x={x + 1.4}
                y={yPos + 7 + lineIndex * 3}
                fontFamily={font(theme)}
                fontSize="2.4"
                fill={text}
              >
                {lineText}
              </text>
            ))}
          </g>
        )
      })}
      {block.end_badge && (
        <g>
          <rect x={boxW - 23} y="3" width="19" height="12" rx="2" fill={resolveColor(theme, 'accent_soft')} />
          <text x={boxW - 13.5} y="10.5" textAnchor="middle" fontFamily={font(theme)} fontSize="3.6" fontWeight="700" fill={accent}>
            {block.end_badge}
          </text>
        </g>
      )}
    </svg>
  )
}

export function ComboChartView({
  block,
  slot,
  theme,
}: {
  block: ComboChartBlock
  slot: Slot
  theme: Theme
}) {
  const categories = block.categories ?? []
  const bars = block.bars?.[0]?.values ?? []
  const lines = (block.lines ?? []).slice(0, 2)
  const count = Math.min(categories.length, bars.length)
  const allValues = [...bars.slice(0, count), ...lines.flatMap((series) => series.values.slice(0, count))]
  const min = Math.min(0, ...allValues)
  const max = Math.max(1, ...allValues)
  const span = max - min || 1
  const y = (value: number) => 78 - ((value - min) / span) * 58
  const colors = theme.palette.chart_series
  const ink = resolveColor(theme, 'ink')
  const muted = resolveColor(theme, 'ink_muted')
  const axis = resolveColor(theme, 'line_strong')
  const boxW = chartBoxWidth(slot)
  const plotLeft = 9
  const plotRight = boxW - 9
  const plotW = plotRight - plotLeft
  const plotStep = plotW / Math.max(count, 1)
  const plotBarW = plotStep * 0.42

  return (
    <svg viewBox={`0 0 ${boxW} 100`} width="100%" height="100%" role="img" aria-label="组合图">
      <line x1={plotLeft} x2={plotRight} y1="78" y2="78" stroke={axis} strokeWidth="0.35" />
      {categories.slice(0, count).map((category, index) => {
        const value = bars[index] ?? 0
        const x = plotLeft + plotStep * index + (plotStep - plotBarW) / 2
        const top = y(value)
        return (
          <g key={`${category}-${index}`}>
            <rect x={x} y={top} width={plotBarW} height={Math.max(78 - top, 1)} fill={colors[index % 2] ?? colors[0]} />
            <text x={x + plotBarW / 2} y={Math.max(top - 2.5, 6)} textAnchor="middle" fontFamily={font(theme)} fontSize="4" fill={ink}>
              {numberLabel(value)}
            </text>
            <text x={x + plotBarW / 2} y="84" textAnchor="middle" fontFamily={font(theme)} fontSize="3.2" fill={muted}>
              {category}
            </text>
          </g>
        )
      })}
      {lines.map((series, seriesIndex) => {
        const color = colors[(seriesIndex + 2) % colors.length]
        const points = series.values.slice(0, count).map((value, index) => ({
          x: plotLeft + plotStep * index + plotStep / 2,
          y: y(value),
          value,
        }))
        return (
          <g key={series.name}>
            <polyline
              points={points.map((point) => `${point.x},${point.y}`).join(' ')}
              fill="none"
              stroke={color}
              strokeWidth="0.7"
            />
            {points.map((point, index) => (
              <g key={`${series.name}-${index}`}>
                <circle cx={point.x} cy={point.y} r="1.1" fill={resolveColor(theme, 'background')} stroke={color} strokeWidth="0.8" />
                <text x={point.x} y={point.y + 5} textAnchor="middle" fontFamily={font(theme)} fontSize="3.1" fill={color}>
                  {numberLabel(point.value)}
                  {block.line_unit ?? ''}
                </text>
              </g>
            ))}
          </g>
        )
      })}
      {(block.annotations ?? []).slice(0, 2).map((annotation, index) => (
        <text
          key={annotation}
          x={boxW / 2 + (index - 0.5) * Math.min(28, boxW * 0.18)}
          y="9"
          textAnchor="middle"
          fontFamily={font(theme)}
          fontSize="4"
          fontWeight="700"
          fill={resolveColor(theme, 'accent')}
        >
          {annotation}
        </text>
      ))}
      <text x={boxW / 2} y="95" textAnchor="middle" fontFamily={font(theme)} fontSize="3.2" fill={muted}>
        {[block.bars?.[0]?.name, ...lines.map((series) => series.name)].filter(Boolean).join('   ')}
      </text>
    </svg>
  )
}
