import standard from '../../../shared/card-layout.json'
import financial from '../../../shared/financial-tech-style.json'
import type { Theme } from './types'

export function cardStyle(visualStyle = 'standard') {
  return visualStyle === 'financial-tech'
    ? { ...standard, gap_pt: financial.card_gap_pt, padding_pt: financial.card_padding_pt,
        min_width_pt: financial.card_min_width_pt, max_columns: financial.card_max_columns }
    : standard
}

export function cardGrid(count: number, width: number, height: number, visualStyle = 'standard') {
  const spec = cardStyle(visualStyle)
  const capacity = Math.max(1, Math.min(count, spec.max_columns,
    Math.floor((width + spec.gap_pt) / (spec.min_width_pt + spec.gap_pt))))
  const rows = Math.max(1, Math.ceil(count / capacity))
  const columns = Math.max(1, Math.ceil(count / rows))
  return { columns, rows,
    width: Math.max(1, (width - spec.gap_pt * (columns - 1)) / columns),
    height: Math.max(1, (height - spec.gap_pt * (rows - 1)) / rows) }
}

export function cardHeaderHeight(height: number, size: number, lineHeight: number) {
  return Math.min(height * 0.45, Math.max(financial.header_min_height_pt, size * lineHeight * 2 + 12))
}

export function cardHeaderInset(width: number) {
  return Math.max(financial.header_padding_pt,
    width * financial.header_notch_ratio + financial.header_safe_padding_pt)
}

export function cardOuterInset(style?: { padding_pt?: number | null; border_width_pt?: number | null;
  border_color?: string | null } | null) {
  return (style?.padding_pt ?? 0) + (style?.border_color ? style.border_width_pt ?? 0 : 0)
}

export function themeCardStyle(theme: Theme) {
  return cardStyle(theme.visual_style)
}
