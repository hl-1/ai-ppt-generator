import { useQueryClient } from '@tanstack/react-query'
import { outlineKey } from '@/features/outline/api'
import type { OutlineProgressEvent } from '@/features/outline/types'
import { useEventStream } from '@/hooks/useEventStream'

const TERMINAL_TYPES = ['completed', 'failed', 'cancelled'] as const

export function useOutlineProgress(projectId: string, active: boolean, jobId?: string | null) {
  const queryClient = useQueryClient()

  const stream = useEventStream<OutlineProgressEvent>({
    path: `/projects/${projectId}/outline/events?job_id=${encodeURIComponent(jobId ?? '')}`,
    active,
    terminalTypes: TERMINAL_TYPES,
    onEvent: (next) => {
      if (next.job_id !== jobId) return
      if (TERMINAL_TYPES.includes(next.type as typeof TERMINAL_TYPES[number])) {
        void queryClient.invalidateQueries({ queryKey: outlineKey(projectId) })
      }
    },
  })
  return { ...stream, event: stream.event?.job_id === jobId ? stream.event : null }
}
