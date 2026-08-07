/**
 * 前后端 flex solver 对齐检查：读 shared/flex-presets/golden-image-left.json。
 * 运行：cd frontend && npx --yes tsx scripts/flex-parity.mts
 */
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { solve, type FlexContainer } from '../src/render/flexLayout.ts'

const here = dirname(fileURLToPath(import.meta.url))
const goldenPath = resolve(here, '../../shared/flex-presets/golden-image-left.json')
const golden = JSON.parse(readFileSync(goldenPath, 'utf8')) as {
  tree: FlexContainer
  expected_rects: Record<string, { x: number; y: number; w: number; h: number }>
}

const placed = Object.fromEntries(solve(golden.tree).map((p) => [p.block_id, p.rect]))

for (const [blockId, expected] of Object.entries(golden.expected_rects)) {
  const actual = placed[blockId]
  assert.ok(actual, `missing rect for ${blockId}`)
  assert.equal(actual.x, expected.x, `${blockId}.x`)
  assert.equal(actual.y, expected.y, `${blockId}.y`)
  assert.equal(actual.w, expected.w, `${blockId}.w`)
  assert.equal(actual.h, expected.h, `${blockId}.h`)
}

console.log('flex parity OK:', Object.keys(golden.expected_rects).join(', '))
