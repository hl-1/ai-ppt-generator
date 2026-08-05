import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { request } from '@/api/client'
import type { Deck, DeckGenerateAccepted } from '@/features/deck/types'

export const deckKey = (projectId: string) => ['projects', projectId, 'deck'] as const
const projectKey = (projectId: string) => ['projects', projectId] as const

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
