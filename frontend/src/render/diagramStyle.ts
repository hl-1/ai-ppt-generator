import flowchartStyle from '../../../shared/flowchart-style.json'
import type { Theme } from './types'

export { flowchartStyle }

export function themedFlowchartStyle(theme: Theme) {
  const p = theme.palette
  const rgb = p.background.match(/[\da-f]{2}/gi)!.map(v => parseInt(v, 16))
  const dark = (rgb[0] * 0.2126 + rgb[1] * 0.7152 + rgb[2] * 0.0722) < 128
  return { ...flowchartStyle, background: p.background, node_fill: p.accent_soft,
    node_border: p.line, text: dark ? p.ink : p.accent, connector: p.ink_muted,
    condition_border: p.accent }
}

export function roundedRoute(points: number[][]): string {
  if (!points.length) return ''
  const commands = [`M${points[0].join(',')}`]
  for (let i = 1; i < points.length - 1; i++) {
    const [px, py] = points[i - 1]
    const [x, y] = points[i]
    const [tx, ty] = points[i + 1]
    const dx = x - px, dy = y - py, nx = tx - x, ny = ty - y
    const before = Math.abs(dx) + Math.abs(dy), after = Math.abs(nx) + Math.abs(ny)
    if (!before || !after || Math.abs(dx * ny - dy * nx) < 0.001) {
      commands.push(`L${x},${y}`)
      continue
    }
    const r = Math.min(flowchartStyle.connector_radius, before / 2, after / 2)
    commands.push(`L${x - dx * r / before},${y - dy * r / before}`)
    commands.push(`Q${x},${y} ${x + nx * r / after},${y + ny * r / after}`)
  }
  if (points.length > 1) commands.push(`L${points.at(-1)!.join(',')}`)
  return commands.join(' ')
}
