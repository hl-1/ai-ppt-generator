import { BlockView } from '@/render/BlockView'
import { getLayout } from '@/render/design'
import { pt, rectToStyle, resolveColor } from '@/render/style'
import {
  CANVAS_HEIGHT_PT,
  CANVAS_WIDTH_PT,
  type EditableBlockCommit,
  type Slide,
  type Theme,
} from '@/render/types'

interface SlideViewProps {
  slide: Slide
  theme: Theme
  editable?: boolean
  selectedBlockId?: string | null
  onSelectBlock?: (blockId: string | null) => void
  onCommit?: (blockId: string, body: EditableBlockCommit) => void
}

/**
 * 通用幻灯片渲染器。
 *
 * 它不认识任何具体布局，只按布局数据把内容块摆到槽位里。
 * PPTX 渲染器做的是同一件事，两端因此天然一致：
 * 新增布局只需增加一份 JSON，两端都不用改代码。
 *
 * 编辑态复用同一棵渲染树：仅把可写字段换成受约束的 contenteditable。
 */
export function SlideView({
  slide,
  theme,
  editable = false,
  selectedBlockId = null,
  onSelectBlock,
  onCommit,
}: SlideViewProps) {
  const layout = getLayout(slide.layout_id)

  return (
    <div
      style={{
        containerType: 'size',
        position: 'relative',
        width: '100%',
        aspectRatio: `${CANVAS_WIDTH_PT} / ${CANVAS_HEIGHT_PT}`,
        background: resolveColor(theme, 'background'),
        overflow: 'hidden',
      }}
      onPointerDown={(event) => {
        if (!editable || !onSelectBlock) return
        // 点在空白处（非 block）才清空选中
        if ((event.target as HTMLElement).closest('[data-block-id]')) return
        onSelectBlock(null)
      }}
    >
      {layout.decorations.map((decoration, index) => (
        <div
          key={`${decoration.type}-${index}`}
          aria-hidden
          style={{
            ...rectToStyle(decoration.rect),
            background: resolveColor(theme, decoration.color),
          }}
        />
      ))}

      {slide.blocks.map((block) => {
        const slot = layout.slots.find((candidate) => candidate.id === block.slot_id)
        if (!slot) return null
        const selected = selectedBlockId === block.id
        const selectable = editable && block.type !== 'chart'

        return (
          <div
            key={block.id}
            data-block-id={block.id}
            style={{
              ...rectToStyle(slot.rect),
              overflow: 'hidden',
              outline: selected
                ? `2px solid ${resolveColor(theme, 'accent')}`
                : '2px solid transparent',
              outlineOffset: selected ? '2px' : 0,
              cursor: selectable ? 'pointer' : undefined,
              zIndex: selected ? 3 : 1,
            }}
            onPointerDown={(event) => {
              if (!selectable || !onSelectBlock) return
              // 不阻断 contenteditable 的聚焦；仅同步选中
              event.stopPropagation()
              onSelectBlock(block.id)
            }}
          >
            {editable && block.locked && (
              <span
                role="img"
                title="已人工修改，AI 不会覆盖"
                aria-label="已人工修改，AI 不会覆盖"
                style={{
                  position: 'absolute',
                  top: pt(4),
                  right: pt(4),
                  zIndex: 2,
                  width: pt(6),
                  height: pt(6),
                  background: resolveColor(theme, 'accent'),
                }}
              />
            )}
            <BlockView
              block={block}
              slot={slot}
              theme={theme}
              editable={editable}
              onCommit={onCommit}
              onSelect={onSelectBlock ?? undefined}
            />
          </div>
        )
      })}
    </div>
  )
}

/** 缩略图：与正式渲染共用同一组件，只是容器更小 */
export function SlideThumbnail({ slide, theme }: SlideViewProps) {
  return (
    <div style={{ border: `1px solid ${resolveColor(theme, 'line')}`, padding: pt(0) }}>
      <SlideView slide={slide} theme={theme} />
    </div>
  )
}
