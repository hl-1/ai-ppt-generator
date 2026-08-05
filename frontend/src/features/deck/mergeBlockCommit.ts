import type { BlockUpdateBody, DeckSlide } from '@/features/deck/types'
import type { EditableBlockCommit } from '@/render/types'

/** 把字段级编辑叠到当前块（含尚未发出的覆盖）上，得到完整 PATCH 体 */
export function mergeBlockCommit(
  slide: DeckSlide,
  blockId: string,
  commit: EditableBlockCommit,
  previous?: BlockUpdateBody,
): BlockUpdateBody | null {
  const block = slide.blocks.find((item) => item.id === blockId)
  if (!block || block.type !== commit.type) return null

  if (commit.type === 'text' && block.type === 'text') {
    return { type: 'text', text: commit.text }
  }

  if (commit.type === 'bullets' && block.type === 'bullets') {
    // 清空的条目先保留占位，避免后续要点的 index 错位；真正提交前再剔除
    const base = previous?.type === 'bullets' ? previous.items : block.items
    const items = base.map((item, index) => (index === commit.index ? commit.text : item))
    return { type: 'bullets', items }
  }

  if (commit.type === 'kpi' && block.type === 'kpi') {
    const base =
      previous?.type === 'kpi'
        ? previous
        : {
            type: 'kpi' as const,
            value: block.value,
            label: block.label,
            note: block.note ?? null,
          }
    return {
      type: 'kpi',
      value: commit.field === 'value' ? commit.text : base.value,
      label: commit.field === 'label' ? commit.text : base.label,
      note:
        commit.field === 'note' ? commit.text || null : (base.note ?? null),
    }
  }

  if (commit.type === 'table' && block.type === 'table') {
    const base =
      previous?.type === 'table'
        ? { header: previous.header, rows: previous.rows }
        : { header: block.header, rows: block.rows }

    if (commit.kind === 'header') {
      return {
        type: 'table',
        header: base.header.map((cell, index) =>
          index === commit.index ? commit.text : cell,
        ),
        rows: base.rows,
      }
    }

    return {
      type: 'table',
      header: base.header,
      rows: base.rows.map((row, rowIndex) =>
        rowIndex === commit.row
          ? row.map((cell, colIndex) =>
              colIndex === commit.col ? commit.text : cell,
            )
          : row,
      ),
    }
  }

  return null
}
