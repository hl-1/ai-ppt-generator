import assert from 'node:assert/strict'
import { mkdir } from 'node:fs/promises'
import { createRequire } from 'node:module'
import { resolve } from 'node:path'

const require = createRequire(import.meta.url)
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright')
const browser = await chromium.launch({ headless: true })
const output = resolve('node_modules/.tmp/financial-tech-qa')
await mkdir(output, { recursive: true })
const errors = []
try {
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } })
  page.on('pageerror', (error) => errors.push(error.message))
  await page.goto(process.env.PREVIEW_URL || 'http://127.0.0.1:39174/themes/financial-tech')
  await page.locator('[data-financial-panels]').first().waitFor()
  await page.screenshot({ path: resolve(output, 'desktop-services.png'), fullPage: true })
  assert.equal(
    await page.locator('[data-financial-panels]').first().locator(':scope > div').count(),
    4,
  )
  await page.getByRole('checkbox', { name: '编辑', exact: true }).check()
  const title = page.getByRole('textbox', { name: '编辑卡片标题 1', exact: true })
  await title.fill('个人金融服务')
  await page.getByRole('heading', { name: '金融科技蓝金', exact: true }).click()
  await page.waitForFunction(() =>
    document.querySelector('nav[aria-label="示例页面"]')?.textContent.includes('个人金融服务'),
  )
  await page.getByRole('checkbox', { name: '编辑', exact: true }).uncheck()
  const downloadPromise = page.waitForEvent('download')
  await page.getByRole('button', { name: '导出 PPTX', exact: true }).click()
  const download = await downloadPromise
  assert.equal(await download.failure(), null)
  await download.saveAs(resolve(output, 'edited-preview.pptx'))
  await page.getByRole('button', { name: '下一页', exact: true }).click()
  await page.locator('[data-financial-platform]').first().waitFor()
  await page.screenshot({ path: resolve(output, 'desktop-platform.png'), fullPage: true })
  const boxes = await page
    .locator('[data-financial-platform]')
    .first()
    .locator(':scope > div')
    .evaluateAll((elements) =>
      elements.map((element) => {
        const rect = element.getBoundingClientRect()
        return { x: rect.x, y: rect.y, w: rect.width, h: rect.height }
      }),
    )
  assert.equal(boxes.length, 7)
  for (let i = 0; i < boxes.length; i++)
    for (let j = i + 1; j < boxes.length; j++) {
      const a = boxes[i],
        b = boxes[j]
      assert.ok(
        Math.min(a.x + a.w, b.x + b.w) - Math.max(a.x, b.x) <= 0 ||
          Math.min(a.y + a.h, b.y + b.h) - Math.max(a.y, b.y) <= 0,
      )
    }
  await page.getByRole('checkbox', { name: '编辑', exact: true }).check()
  const node = page.getByRole('textbox', { name: '编辑流程节点 1 标题', exact: true })
  await node.fill('综合金融平台')
  await page.getByRole('heading', { name: '金融科技蓝金', exact: true }).click()
  await page.waitForFunction(() =>
    document.querySelector('nav[aria-label="示例页面"]')?.textContent.includes('综合金融平台'),
  )
  await page.getByRole('checkbox', { name: '编辑', exact: true }).uncheck()
  await page.getByRole('button', { name: '下一页', exact: true }).click()
  await page.screenshot({ path: resolve(output, 'desktop-architecture.png'), fullPage: true })
  for (const position of [1, 2, 3]) {
    await page.getByRole('button', { name: `第 ${position} 页`, exact: true }).click()
    assert.equal(
      await page.locator('main').evaluate((el) => el.scrollWidth > window.innerWidth + 1),
      false,
    )
  }
  await page.getByRole('combobox', { name: '主题', exact: true }).selectOption('enterprise-dark')
  await page.waitForURL('**/themes/enterprise-dark')
  await page.waitForFunction(
    () => document.querySelectorAll('[data-financial-panels]').length === 0,
  )
  assert.equal(await page.locator('[data-financial-panels]').count(), 0)
  await page.getByRole('combobox', { name: '主题', exact: true }).selectOption('financial-tech')
  await page.waitForURL('**/themes/financial-tech')
  await page.locator('[data-financial-panels]').first().waitFor()
  await page.setViewportSize({ width: 390, height: 844 })
  for (const position of [1, 2, 3]) {
    await page.getByRole('button', { name: `第 ${position} 页`, exact: true }).click()
    await page.screenshot({ path: resolve(output, `mobile-${position}.png`), fullPage: true })
    assert.equal(
      await page.locator('main').evaluate((el) => el.scrollWidth > window.innerWidth + 1),
      false,
    )
  }
  assert.deepEqual(errors, [])
  console.log(
    `Browser checks passed: desktop/mobile, cards/nodes editing, theme switching, native PPTX download. ${output}`,
  )
} finally {
  await browser.close()
}
