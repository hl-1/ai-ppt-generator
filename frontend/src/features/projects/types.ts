import type { components } from '@/api/schema'

type Schemas = components['schemas']

export type Project = Schemas['ProjectPublic']
export type ProjectDetail = Schemas['ProjectDetail']
export type ProjectCreate = Schemas['ProjectCreate']
export type ProjectUpdate = Schemas['ProjectUpdate']
export type ProjectSource = Schemas['SourcePublic']
export type SourceSection = Schemas['SourceSection']
export type Tone = ProjectCreate['tone']

export const TONE_LABEL: Record<NonNullable<Tone>, string> = {
  professional: '专业严谨',
  plain: '通俗易懂',
  punchy: '简洁有力',
}

export const STATUS_LABEL: Record<Project['status'], string> = {
  draft: '待生成大纲',
  outline_ready: '大纲已确认',
  generating: '正在生成',
  ready: '可导出',
}

export const SOURCE_KIND_LABEL: Record<ProjectSource['kind'], string> = {
  topic: '主题',
  text: '长文本',
  document: '文档',
}

export const PAGE_COUNT_RANGE = { min: 5, max: 20 } as const
export const ACCEPTED_UPLOAD = '.pdf,.docx,.md,.markdown,.txt'
