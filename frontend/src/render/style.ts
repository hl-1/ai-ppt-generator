import type { CSSProperties } from 'react'
import {
  CANVAS_HEIGHT_PT,
  CANVAS_WIDTH_PT,
  type ColorToken,
  type Rect,
  type TextStyleName,
  type Theme,
} from '@/render/types'

export function resolveColor(theme: Theme, token: ColorToken | string): string {
  // 元素覆盖后可能是 #RRGGBB，直接透传
  if (/^#[0-9A-Fa-f]{6}$/.test(token)) return token.toUpperCase()
  const value = (theme.palette as Record<string, unknown>)[token]
  if (typeof value !== 'string') throw new Error(`主题 ${theme.id} 不存在颜色令牌：${token}`)
  return value
}

/** 槽位矩形换算为绝对定位百分比，与画布尺寸无关 */
export function rectToStyle(rect: Rect): CSSProperties {
  return {
    position: 'absolute',
    left: `${rect.x * 100}%`,
    top: `${rect.y * 100}%`,
    width: `${rect.w * 100}%`,
    height: `${rect.h * 100}%`,
  }
}

/**
 * pt 换算为 CSS 长度。1 个基准画布宽度等于 CANVAS_WIDTH_PT，
 * 因此用容器查询单位 cqw 表达，缩略图与全屏预览自动等比。
 */
export function pt(value: number): string {
  return `${(value / CANVAS_WIDTH_PT) * 100}cqw`
}

export function ptVertical(value: number): string {
  return `${(value / CANVAS_HEIGHT_PT) * 100}cqh`
}

export function textStyleToCss(theme: Theme, name: TextStyleName): CSSProperties {
  const style = theme.text_styles[name]
  if (!style) throw new Error(`主题 ${theme.id} 未定义文本样式：${name}`)

  const family = style.font === 'display' ? theme.fonts.display : theme.fonts.body

  return {
    fontFamily: family.web,
    fontSize: pt(style.size_pt),
    lineHeight: style.line_height,
    fontWeight: style.weight,
    letterSpacing: style.letter_spacing_pt === 0 ? undefined : pt(style.letter_spacing_pt),
    color: resolveColor(theme, style.color),
  }
}
