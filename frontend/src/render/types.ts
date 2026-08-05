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
export type ColorToken = TextStyle['color']

/** 16:9 基准画布，单位 pt。必须与后端 app/domain/geometry.py 保持一致 */
export const CANVAS_WIDTH_PT = 960
export const CANVAS_HEIGHT_PT = 540
