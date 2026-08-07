import type { FlexBlockType } from '@/features/deck/flexTree'
import type { DeckSlide } from '@/features/deck/types'
import type { FlexContainer } from '@/render/flexLayout'

export type SlideSaveHandlers = {
  commitFlex: (tree: FlexContainer) => void
  commitCreateBlock: (body: {
    type: FlexBlockType
    parent_id: string
    index?: number
  }) => void
  commitDeleteBlock: (blockId: string) => void
  commitMutate: (run: (slide: DeckSlide) => Promise<DeckSlide>) => void
  undo: () => boolean
}

const registry = new Map<string, SlideSaveHandlers>()

/** SlidePage 挂载时注册，供侧栏/换排布等跨树组件走同一保存队列 */
export function registerSlideSaveHandlers(
  slideId: string,
  handlers: SlideSaveHandlers,
): () => void {
  registry.set(slideId, handlers)
  return () => {
    if (registry.get(slideId) === handlers) registry.delete(slideId)
  }
}

export function getSlideSaveHandlers(slideId: string): SlideSaveHandlers | null {
  return registry.get(slideId) ?? null
}
