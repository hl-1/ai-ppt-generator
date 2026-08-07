import {
  BarChart3,
  Columns2,
  Columns3,
  Hash,
  Image as ImageIcon,
  List,
  Loader2,
  Table2,
  Type,
} from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import {
  createSlideBlock,
  updateFlexLayout,
} from '@/features/deck/api'
import {
  type FlexBlockType,
  findContainerById,
  resolveInsertAnchor,
  wrapBlockIdsAsColumns,
} from '@/features/deck/flexTree'
import { getSlideSaveHandlers } from '@/features/deck/slideSaveBridge'
import type { DeckSlide } from '@/features/deck/types'
import { errorMessage } from '@/lib/errors'
import { cn } from '@/lib/utils'
import type { FlexContainer } from '@/render/flexLayout'

const BLOCK_BUTTONS: Array<{
  type: FlexBlockType
  label: string
  icon: typeof Type
}> = [
  { type: 'text', label: '文本', icon: Type },
  { type: 'bullets', label: '列表', icon: List },
  { type: 'image', label: '图片', icon: ImageIcon },
  { type: 'kpi', label: 'KPI', icon: Hash },
  { type: 'table', label: '表格', icon: Table2 },
  { type: 'chart', label: '图表', icon: BarChart3 },
]

export type InsertAnchor = { parentId: string; index: number }

async function insertColumnsAt(
  projectId: string,
  slide: DeckSlide,
  anchor: InsertAnchor,
  count: 2 | 3,
): Promise<DeckSlide> {
  let current = slide
  const before = new Set(current.blocks.map((block) => block.id))
  let insertAt = anchor.index

  for (let i = 0; i < count; i++) {
    current = await createSlideBlock(projectId, slide.id, {
      revision: current.revision,
      type: 'text',
      parent_id: anchor.parentId,
      index: insertAt,
    })
    insertAt += 1
  }

  const newIds = current.blocks
    .filter((block) => !before.has(block.id) && block.type === 'text')
    .map((block) => block.id)
    .slice(-count)

  if (newIds.length !== count || current.layout_tree == null) {
    throw new Error('列插入未得到预期内容块')
  }

  const tree = current.layout_tree as FlexContainer
  const parent = findContainerById(tree, anchor.parentId)
  if (!parent) throw new Error('插入目标容器不存在')
  const wrapped = wrapBlockIdsAsColumns(tree, newIds)
  if (!wrapped) throw new Error('无法组装多列布局')

  return updateFlexLayout(projectId, slide.id, {
    revision: current.revision,
    layout_tree: wrapped,
  })
}

/**
 * 画布就地插入菜单：出现在间隙 + 旁。
 */
export function InsertMenu({
  projectId,
  slide,
  anchor,
  disabled,
  onClose,
  onDone,
}: {
  projectId: string
  slide: DeckSlide
  anchor: InsertAnchor
  disabled?: boolean
  onClose: () => void
  onDone?: () => void
}) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const rootRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault()
        onClose()
      }
    }
    const onPointer = (event: PointerEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) onClose()
    }
    window.addEventListener('keydown', onKey)
    window.addEventListener('pointerdown', onPointer, true)
    return () => {
      window.removeEventListener('keydown', onKey)
      window.removeEventListener('pointerdown', onPointer, true)
    }
  }, [onClose])

  if (slide.layout_mode !== 'flex' || slide.layout_tree == null) return null

  const handlers = getSlideSaveHandlers(slide.id)
  const locked = Boolean(disabled || busy || !handlers)

  const insertBlock = (type: FlexBlockType) => {
    if (locked || !handlers) return
    setError(null)
    handlers.commitCreateBlock({
      type,
      parent_id: anchor.parentId,
      index: anchor.index,
    })
    onDone?.()
    onClose()
  }

  const insertColumns = (count: 2 | 3) => {
    if (locked || !handlers) return
    setBusy(true)
    setError(null)
    handlers.commitMutate((current) =>
      insertColumnsAt(projectId, current, anchor, count),
    )
    onDone?.()
    onClose()
    setBusy(false)
  }

  return (
    <div
      ref={rootRef}
      role="menu"
      aria-label="插入内容"
      className="pointer-events-auto absolute z-30 w-44 rounded-xl border border-line bg-surface p-1.5 shadow-pop"
      onPointerDown={(event) => event.stopPropagation()}
    >
      <InsertButtons
        locked={locked}
        busy={busy}
        onInsertBlock={insertBlock}
        onInsertColumns={insertColumns}
        compact
      />
      {error && (
        <p role="alert" className="mt-1 px-1 text-[11px] text-negative">
          {error}
        </p>
      )}
    </div>
  )
}

/**
 * 版式侧栏插入条：打开版式面板时显示，非常驻。
 */
export function BlockInsertPanel({
  projectId,
  slide,
  selectedBlockId,
  disabled,
}: {
  projectId: string
  slide: DeckSlide
  selectedBlockId: string | null
  disabled?: boolean
}) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  if (slide.layout_mode !== 'flex' || slide.layout_tree == null) return null

  const tree = slide.layout_tree as FlexContainer
  const anchor = resolveInsertAnchor(tree, selectedBlockId)
  const handlers = getSlideSaveHandlers(slide.id)
  const locked = Boolean(disabled || busy || !handlers)

  const insertBlock = (type: FlexBlockType) => {
    if (locked || !handlers) return
    setError(null)
    handlers.commitCreateBlock({
      type,
      parent_id: anchor.parentId,
      index: anchor.index,
    })
  }

  const insertColumns = (count: 2 | 3) => {
    if (locked || !handlers) return
    setBusy(true)
    setError(null)
    try {
      handlers.commitMutate((current) =>
        insertColumnsAt(projectId, current, anchor, count),
      )
    } catch (err) {
      setError(errorMessage(err, '插入列失败'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="rounded-xl border border-line bg-surface-soft/40 p-3">
      <p className="mb-2 text-[12px] font-medium text-ink-soft">插入内容</p>
      <InsertButtons
        locked={locked}
        busy={busy}
        onInsertBlock={insertBlock}
        onInsertColumns={insertColumns}
      />
      {error && (
        <p role="alert" className="mt-2 text-[11px] text-negative">
          {error}
        </p>
      )}
    </div>
  )
}

function InsertButtons({
  locked,
  busy,
  onInsertBlock,
  onInsertColumns,
  compact,
}: {
  locked: boolean
  busy: boolean
  onInsertBlock: (type: FlexBlockType) => void
  onInsertColumns: (count: 2 | 3) => void
  compact?: boolean
}) {
  return (
    <>
      <div className={cn('grid gap-0.5', compact ? 'grid-cols-3' : 'grid-cols-3')}>
        {BLOCK_BUTTONS.map(({ type, label, icon: Icon }) => (
          <button
            key={type}
            type="button"
            role="menuitem"
            title={label}
            disabled={locked}
            onClick={() => onInsertBlock(type)}
            className={cn(
              'flex flex-col items-center gap-1 rounded-lg text-[11px] transition-colors',
              compact ? 'px-1 py-2' : 'px-1.5 py-2.5',
              'text-ink-soft hover:bg-surface hover:text-ink',
              'disabled:opacity-40',
            )}
          >
            <Icon className="size-3.5" />
            {label}
          </button>
        ))}
      </div>
      <div
        className={cn(
          'grid grid-cols-2 gap-0.5 border-t border-line',
          compact ? 'mt-1 pt-1' : 'mt-2 pt-2',
        )}
      >
        <button
          type="button"
          role="menuitem"
          disabled={locked}
          onClick={() => onInsertColumns(2)}
          className="flex items-center justify-center gap-1 rounded-lg px-2 py-1.5 text-[11px] text-ink-soft hover:bg-surface hover:text-ink disabled:opacity-40"
        >
          {busy ? <Loader2 className="size-3 animate-spin" /> : <Columns2 className="size-3.5" />}
          2 列
        </button>
        <button
          type="button"
          role="menuitem"
          disabled={locked}
          onClick={() => onInsertColumns(3)}
          className="flex items-center justify-center gap-1 rounded-lg px-2 py-1.5 text-[11px] text-ink-soft hover:bg-surface hover:text-ink disabled:opacity-40"
        >
          {busy ? <Loader2 className="size-3 animate-spin" /> : <Columns3 className="size-3.5" />}
          3 列
        </button>
      </div>
    </>
  )
}
