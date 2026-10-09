import type { components } from '@/api/schema'

type Schemas = components['schemas']

export type Outline = Schemas['OutlinePublic']
export type OutlinePage = Schemas['OutlinePage']
export type OutlineUpdate = Schemas['OutlineUpdate']
export type OutlineGenerateAccepted = Schemas['OutlineGenerateAccepted']
export type OutlineExecution = Schemas['OutlineExecution']
export type OutlineStageExecution = Schemas['OutlineStageExecution']

export type OutlineErrorCode = NonNullable<Schemas['OutlinePublic']['error_code']>
export type OutlineStage = OutlineStageExecution['stage']
export type OutlineProgressEvent = Schemas['OutlineEvent']
