import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { request } from '@/api/client'
import { replaceSlideInDeck, replaceSlidesInDeck } from '@/features/deck/cache'
import type {
  AiEditAction,
  AiEditPatch,
  AiEditProposal,
  BlockUpdateBody,
  Deck,
  DeckGenerateAccepted,
  DeckSlide,
  LayoutCandidate,
} from '@/features/deck/types'

export const deckKey = (projectId: string) => ['projects', projectId, 'deck'] as const
const projectKey = (projectId: string) => ['projects', projectId] as const
const slideLayoutsKey = (projectId: string, slideId: string) =>
  ['projects', projectId, 'deck', 'slides', slideId, 'layouts'] as const

export function useDeck(projectId: string, enabled = true) {
  return useQuery({
    queryKey: deckKey(projectId),
    queryFn: () => request<Deck>(`/projects/${projectId}/deck`),
    enabled,
  })
}

/** 三个写操作只有路径与请求体不同，成功后都要刷新页面列表与项目状态 */
function useDeckMutation<TVariables>(
  projectId: string,
  toRequest: (variables: TVariables) => { path: string; body?: unknown },
) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (variables: TVariables) => {
      const { path, body } = toRequest(variables)
      return request<DeckGenerateAccepted | null>(path, {
        method: 'POST',
        body: body === undefined ? undefined : JSON.stringify(body),
      })
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: deckKey(projectId) })
      void queryClient.invalidateQueries({ queryKey: projectKey(projectId) })
    },
  })
}

export function useGenerateDeck(projectId: string) {
  return useDeckMutation<{ regenerateAll: boolean }>(projectId, ({ regenerateAll }) => ({
    path: `/projects/${projectId}/deck/generate`,
    body: { regenerate_all: regenerateAll },
  }))
}

export function useRetrySlide(projectId: string) {
  return useDeckMutation<string>(projectId, (slideId) => ({
    path: `/projects/${projectId}/deck/slides/${slideId}/retry`,
  }))
}

export function useCancelDeck(projectId: string) {
  return useDeckMutation<void>(projectId, () => ({
    path: `/projects/${projectId}/deck/cancel`,
  }))
}

interface ReplaceImageInput {
  slideId: string
  blockId: string
  revision: number
  file: File
}

export function useReplaceSlideImage(projectId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ slideId, blockId, revision, file }: ReplaceImageInput) => {
      const form = new FormData()
      form.append('file', file)
      // 带上版本号：换图期间这一页可能刚被 AI 改过，冲突要由服务端判定
      form.append('revision', String(revision))
      return request<DeckSlide>(
        `/projects/${projectId}/deck/slides/${slideId}/blocks/${blockId}/image`,
        { method: 'PUT', body: form },
      )
    },
    onSuccess: (slide) => {
      queryClient.setQueryData<Deck>(deckKey(projectId), (current) =>
        replaceSlideInDeck(current, slide),
      )
    },
  })
}

export function updateSlideBlock(
  projectId: string,
  slideId: string,
  blockId: string,
  body: BlockUpdateBody & { revision: number },
) {
  return request<DeckSlide>(
    `/projects/${projectId}/deck/slides/${slideId}/blocks/${blockId}`,
    { method: 'PATCH', body: JSON.stringify(body) },
  )
}

export function useReorderSlides(projectId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (slideIds: string[]) =>
      request<DeckSlide[]>(`/projects/${projectId}/deck/slides/order`, {
        method: 'PUT',
        body: JSON.stringify({ slide_ids: slideIds }),
      }),
    onMutate: async (slideIds) => {
      await queryClient.cancelQueries({ queryKey: deckKey(projectId) })
      const previous = queryClient.getQueryData<Deck>(deckKey(projectId))
      if (previous) {
        const byId = new Map(previous.slides.map((slide) => [slide.id, slide]))
        const slides = slideIds.flatMap((id, index) => {
          const slide = byId.get(id)
          return slide ? [{ ...slide, position: index + 1 }] : []
        })
        queryClient.setQueryData<Deck>(deckKey(projectId), { ...previous, slides })
      }
      return { previous }
    },
    onError: (_error, _slideIds, context) => {
      if (context?.previous) {
        queryClient.setQueryData(deckKey(projectId), context.previous)
      }
    },
    onSuccess: (slides) => {
      queryClient.setQueryData<Deck>(deckKey(projectId), (current) =>
        replaceSlidesInDeck(current, slides),
      )
    },
  })
}

export function useSlideLayouts(projectId: string, slideId: string, enabled: boolean) {
  return useQuery({
    queryKey: slideLayoutsKey(projectId, slideId),
    queryFn: () =>
      request<LayoutCandidate[]>(`/projects/${projectId}/deck/slides/${slideId}/layouts`),
    enabled,
  })
}

export function useSwitchSlideLayout(projectId: string, slideId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: { layout_id: string; revision: number }) =>
      request<DeckSlide>(`/projects/${projectId}/deck/slides/${slideId}/layout`, {
        method: 'PUT',
        body: JSON.stringify(body),
      }),
    onSuccess: (slide) => {
      queryClient.setQueryData<Deck>(deckKey(projectId), (current) =>
        replaceSlideInDeck(current, slide),
      )
      void queryClient.invalidateQueries({ queryKey: slideLayoutsKey(projectId, slideId) })
    },
  })
}

export function useProposeAiEdit(projectId: string, slideId: string) {
  return useMutation({
    mutationFn: (body: { action: AiEditAction; revision: number; instruction?: string }) => {
      const payload: { action: AiEditAction; revision: number; instruction?: string } = {
        action: body.action,
        revision: body.revision,
      }
      if (body.instruction) payload.instruction = body.instruction
      return request<AiEditProposal>(
        `/projects/${projectId}/deck/slides/${slideId}/ai-edit`,
        { method: 'POST', body: JSON.stringify(payload) },
      )
    },
  })
}

export function useApplyAiEdit(projectId: string, slideId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: { revision: number; operations: AiEditPatch[] }) =>
      request<DeckSlide>(`/projects/${projectId}/deck/slides/${slideId}/ai-edit/apply`, {
        method: 'POST',
        body: JSON.stringify(body),
      }),
    onSuccess: (slide) => {
      queryClient.setQueryData<Deck>(deckKey(projectId), (current) =>
        replaceSlideInDeck(current, slide),
      )
    },
  })
}
