import type { components } from '@/api/schema'
import type { FlexContainer } from '@/render/flexLayout'
import type { ImageBlock, Slide } from '@/render/types'

type Schemas = components['schemas']

export const ACCEPTED_IMAGE = 'image/png,image/jpeg,image/webp'

export type Deck = Schemas['DeckPublic']
export type DeckSlide = Schemas['SlidePublic']
export type DeckStatus = Deck['status']
export type SlideStatus = DeckSlide['status']
export type DeckGenerateAccepted = Schemas['DeckGenerateAccepted']
export type LayoutCandidate = Schemas['LayoutCandidatePublic']
export type AiEditAction = Schemas['AiEditRequest']['action']
export type AiEditProposal = Schemas['AiEditProposalPublic']
export type AiEditOperation = Schemas['AiEditOperationPublic']
export type AiEditPatch =
  | Schemas['TextPatch']
  | Schemas['BulletsPatch']
  | Schemas['KpiPatch']
  | Schemas['TablePatch']
export type DiscardedOperation = Schemas['DiscardedOperationPublic']
export type StructureIssue = Schemas['StructureIssue']
export type ExportCheckReport = Schemas['ExportCheckReport']

/** relayout 接口尚未写入 OpenAPI schema 时的本地契约 */
export interface RelayoutCandidate {
  id: string
  layout_tree: FlexContainer
}
export interface RelayoutProposal {
  revision: number
  candidates: RelayoutCandidate[]
}
/** 回读验证问题不在 OpenAPI schema 里，与后端 VerifyIssue 字段对齐 */
export interface ExportVerifyIssue {
  check: string
  slide_index: number | null
  shape: string | null
  message: string
}
export type ChartBlockUpdate = {
  type: 'chart'
  revision: number
  chart_type: 'bar' | 'column' | 'line' | 'pie'
  categories: string[]
  series: Array<{ name: string; values: number[] }>
  unit?: string | null
}

export type BlockUpdate =
  | Schemas['TextBlockUpdate']
  | Schemas['BulletsBlockUpdate']
  | Schemas['KpiBlockUpdate']
  | Schemas['TableBlockUpdate']
  | ChartBlockUpdate
/** Omit 不会自动分发联合类型，需逐个剥掉 revision */
export type BlockUpdateBody =
  | Omit<Schemas['TextBlockUpdate'], 'revision'>
  | Omit<Schemas['BulletsBlockUpdate'], 'revision'>
  | Omit<Schemas['KpiBlockUpdate'], 'revision'>
  | Omit<Schemas['TableBlockUpdate'], 'revision'>
  | Omit<ChartBlockUpdate, 'revision'>

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

export function imageBlocks(slide: DeckSlide): ImageBlock[] {
  return slide.blocks.filter((block): block is ImageBlock => block.type === 'image')
}

/** 胶片标题优先用画布上的 title 槽，避免改字后侧栏仍显示大纲旧标题 */
export function slideDisplayTitle(slide: DeckSlide): string {
  const title = slide.blocks.find(
    (block) => block.type === 'text' && block.slot_id === 'title',
  )
  const text = title?.type === 'text' ? title.text.trim() : ''
  return text || slide.title
}

/** 落库的页面转成渲染器认识的内容模型：两者字段同源，只是多了生成状态 */
export function toRenderSlide(slide: DeckSlide): Slide {
  return {
    id: slide.id,
    layout_id: slide.layout_id,
    layout_mode: slide.layout_mode,
    layout_tree: slide.layout_tree,
    blocks: slide.blocks,
    speaker_notes: slide.speaker_notes,
    revision: slide.revision,
  }
}
