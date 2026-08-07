import type { components } from '@/api/schema'

type Schemas = components['schemas']

export type Deck = Schemas['Deck']
export type Slide = Schemas['Slide']
export type Block = Slide['blocks'][number]
export type TextBlock = Schemas['TextBlock']
export type BulletsBlock = Schemas['BulletsBlock']
export type ImageBlock = Schemas['ImageBlock']
export type ChartBlock = Schemas['ChartBlock']
export type TableBlock = Schemas['TableBlock']
export type KpiBlock = Schemas['KpiBlock']

export type Layout = Schemas['Layout']
export type Slot = Schemas['Slot']
export type Decoration = Schemas['Decoration']
export type Rect = Schemas['Rect']

export type Theme = Schemas['Theme']
export type TextStyle = Schemas['TextStyle']
export type TextStyleName = NonNullable<Slot['text_style']>
/** 色令牌从 palette 键派生；TextStyle.color 放宽后可能是 hex */
export type ColorToken = Exclude<keyof Theme['palette'], 'chart_series'>

/** 16:9 基准画布，单位 pt。必须与后端 app/domain/geometry.py 保持一致 */
export const CANVAS_WIDTH_PT = 960
export const CANVAS_HEIGHT_PT = 540

/** 就地编辑的字段级变更；多字段块由保存队列合并，避免并发丢字 */
export type EditableBlockCommit =
  | { type: 'text'; text: string }
  | { type: 'bullets'; index: number; text: string }
  | { type: 'kpi'; field: 'value' | 'label' | 'note'; text: string }
  | { type: 'table'; kind: 'header'; index: number; text: string }
  | { type: 'table'; kind: 'cell'; row: number; col: number; text: string }
  | { type: 'table'; kind: 'replace'; header: string[]; rows: string[][] }
  | {
      type: 'chart'
      chart_type: ChartBlock['chart_type']
      categories: string[]
      series: ChartBlock['series']
      unit?: string | null
    }
  | { type: 'style'; style: import('@/render/blockStyle').BlockStyle | null }
