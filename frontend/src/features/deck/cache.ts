import type { Deck, DeckSlide } from '@/features/deck/types'

export function imageCoverage(deck: Deck) {
  const blocks = deck.slides.filter((slide) => slide.status === 'ready')
    .flatMap((slide) => slide.blocks).filter((block) => block.type === 'image')
  const seen = new Set<string>()
  let ready = 0
  let duplicates = 0
  let pending = 0
  let failed = 0
  const unfilled = Math.max(0, (deck.images?.planned ?? blocks.length) - blocks.length)
  let missing = unfilled
  for (const block of blocks) {
    const queued = block.image_status === 'queued'
      && Date.now() / 1000 - (block.image_job_started_at ?? 0) < 15 * 60
    if (queued) pending += 1
    else if (block.image_status === 'failed' || block.image_status === 'queued') failed += 1
    if (block.url && block.source !== 'placeholder') {
      const identities = [`url:${block.url}`]
      if (block.image_asset_id) identities.push(`asset:${block.image_asset_id}`)
      if (identities.some((identity) => seen.has(identity))) duplicates += 1
      else ready += 1
      identities.forEach((identity) => seen.add(identity))
    } else if (!queued && block.image_status !== 'failed' && block.image_status !== 'queued') {
      missing += 1
    }
  }
  return { ready, pending, failed, missing, duplicates, planned: blocks.length + unfilled,
    minimum: deck.images?.minimum ?? Math.min(2, deck.total) }
}

/** 用单页响应替换 deck 缓存里对应页，避免 invalidate 冲掉正在编辑的 DOM */
export function replaceSlideInDeck(deck: Deck | undefined, slide: DeckSlide): Deck | undefined {
  if (!deck) return deck
  return {
    ...deck,
    slides: deck.slides.map((item) => (item.id === slide.id ? slide : item)),
  }
}

export function replaceSlidesInDeck(deck: Deck | undefined, slides: DeckSlide[]): Deck | undefined {
  if (!deck) return deck
  return { ...deck, slides, total: slides.length }
}
