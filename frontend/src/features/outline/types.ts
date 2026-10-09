import type { components } from '@/api/schema'

type Schemas = components['schemas']

export type Outline = Schemas['OutlinePublic']
export type OutlinePage = Schemas['OutlinePage']
export type OutlineUpdate = Schemas['OutlineUpdate']
export type OutlineGenerateAccepted = Schemas['OutlineGenerateAccepted']

export type OutlineErrorCode = NonNullable<Schemas['OutlinePublic']['error_code']>
export type OutlineStage = 'queue' | 'load_input' | 'travel_research' | 'plan_structure' | 'validate' | 'save'

export interface OutlineProgressEvent {
  type: 'snapshot' | 'progress' | 'completed' | 'failed'
  status: Outline['status']
  progress: number
  message: string
  revision?: number | null
  stage?: OutlineStage | null
  stage_status?: 'started' | 'succeeded' | 'failed' | null
  error_code?: OutlineErrorCode | null
}
