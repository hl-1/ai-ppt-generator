import { useQuery } from '@tanstack/react-query'
import { request } from '@/api/client'

export type ComponentState = 'ok' | 'down'

export interface HealthResponse {
  status: string
  database: ComponentState
  redis: ComponentState
}

export function useHealth() {
  return useQuery({
    queryKey: ['health'],
    queryFn: () => request<HealthResponse>('/health'),
    refetchInterval: 10_000,
  })
}
