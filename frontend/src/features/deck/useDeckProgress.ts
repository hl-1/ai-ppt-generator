import { useQueryClient } from '@tanstack/react-query'
import { deckKey } from '@/features/deck/api'
import type { DeckProgressEvent } from '@/features/deck/types'
import { useEventStream } from '@/hooks/useEventStream'

const TERMINAL_TYPES = ['completed', 'cancelled', 'failed'] as const

export function useDeckProgress(projectId: string, active: boolean) {
  const queryClient = useQueryClient()

  return useEventStream<DeckProgressEvent>({
    path: `/projects/${projectId}/deck/events`,
    active,
    terminalTypes: TERMINAL_TYPES,
    // 每页完成都重新拉一次：页面内容本身不走事件推送，
    // 事件只负责告诉前端"现在有新内容可读了"
    onEvent: () => void queryClient.invalidateQueries({ queryKey: deckKey(projectId) }),
  })
}
