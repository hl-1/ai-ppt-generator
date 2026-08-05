import type { components } from '@/api/schema'
import type { ImageBlock, Slide } from '@/render/types'

type Schemas = components['schemas']

export const ACCEPTED_IMAGE = 'image/png,image/jpeg,image/webp'

export type Deck = Schemas['DeckPublic']
export type DeckSlide = Schemas['SlidePublic']
export type DeckStatus = Deck['status']
export type SlideStatus = DeckSlide['status']
export type DeckGenerateAccepted = Schemas['DeckGenerateAccepted']
export type LayoutCandidate = Schemas['LayoutCandidatePublic']
export type BlockUpdate =
  | Schemas['TextBlockUpdate']
  | Schemas['BulletsBlockUpdate']
  | Schemas['KpiBlockUpdate']
  | Schemas['TableBlockUpdate']
/** Omit 不会自动分发联合类型，需逐个剥掉 revision */
export type BlockUpdateBody =
  | Omit<Schemas['TextBlockUpdate'], 'revision'>
  | Omit<Schemas['BulletsBlockUpdate'], 'revision'>
  | Omit<Schemas['KpiBlockUpdate'], 'revision'>
  | Omit<Schemas['TableBlockUpdate'], 'revision'>

export interface DeckProgressEvent {
  type:
    | 'snapshot'
    | 'slide_started'
    | 'slide_completed'
    | 'slide_failed'
    | 'completed'
    | 'cancelled'
    | 'failed'
  status: DeckStatus
  progress: number
  message: string
  slide_id?: string | null
  position?: number | null
  ready: number
  failed: number
  total: number
}

export const SLIDE_STATUS_LABEL: Record<SlideStatus, string> = {
  pending: '待生成',
  generating: '生成中',
  ready: '已完成',
  failed: '失败',
}

export function imageBlocks(slide: DeckSlide): ImageBlock[] {
  return slide.blocks.filter((block): block is ImageBlock => block.type === 'image')
}

/** 落库的页面转成渲染器认识的内容模型：两者字段同源，只是多了生成状态 */
export function toRenderSlide(slide: DeckSlide): Slide {
  return {
    id: slide.id,
    layout_id: slide.layout_id,
    blocks: slide.blocks,
    speaker_notes: slide.speaker_notes,
    revision: slide.revision,
  }
}
