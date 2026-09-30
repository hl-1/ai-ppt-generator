import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { panelGrid, platformNodeRects } from '../src/render/financialTech.ts'
import type { DiagramNode, DiagramEdge } from '../src/render/types.ts'

type Fixture = {
  nodes: DiagramNode[]
  edges: DiagramEdge[]
  width: number
  height: number
  hub: string | null
  rects: Record<string, Record<string, number>>
}
const fixture = JSON.parse(
  readFileSync(new URL('../../shared/financial-tech-fixtures.json', import.meta.url), 'utf8'),
)
for (const item of fixture.diagrams as Fixture[]) {
  const actual = platformNodeRects(item.nodes, item.edges, item.width, item.height)
  assert.equal(actual.hub, item.hub)
  assert.equal(actual.rects.size, Object.keys(item.rects).length)
  for (const [id, rect] of actual.rects) {
    for (const key of ['x', 'y', 'w', 'h'] as const)
      assert.ok(Math.abs(rect[key] - item.rects[id][key]) < 1e-6)
  }
}
for (const item of fixture.panels) {
  const actual = panelGrid(item.count, item.width, item.height)
  assert.deepEqual([actual.columns, actual.width, actual.height], item.expected)
}
console.log(
  `Financial theme parity passed: ${fixture.diagrams.length} diagrams, ${fixture.panels.length} panels`,
)
