import { useQuery } from '@tanstack/react-query'
import { request } from '@/api/client'
import type { Deck } from '@/render/types'

export function useSampleDeck() {
  return useQuery({
    queryKey: ['design', 'sample-deck'],
    queryFn: () => request<Deck>('/design/sample-deck'),
    staleTime: Infinity,
  })
}
