import { BlockView } from '@/render/BlockView'
import { getLayout } from '@/render/design'
import { solve, type FlexContainer } from '@/render/flexLayout'
import { iterSkinDecorations, type SkinDecoration } from '@/render/flexSkin'
import { pt, rectToStyle, resolveColor } from '@/render/style'
import {
  CANVAS_HEIGHT_PT,
  CANVAS_WIDTH_PT,
  type Block,
  type EditableBlockCommit,
  type Rect,
  type Slide,
  type Slot,
  type TextStyleName,
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

type PlacedEntry = { rect: Rect; text_style?: string | null }

function isFlexMode(slide: Slide): slide is Slide & { layout_tree: FlexContainer } {
  return slide.layout_mode === 'flex' && slide.layout_tree != null
}

/** flex 模式无布局槽位时，为 BlockView 构造最小伪槽（几何与 text_style 来自 solver） */
function flexPseudoSlot(block: Block, placed: PlacedEntry): Slot {
  return {
    id: block.slot_id,
    accepts: [block.type],
    rect: placed.rect,
    required: true,
    text_style: (placed.text_style ?? undefined) as TextStyleName | null | undefined,
    capacity: {},
  }
}

/**
 * 通用幻灯片渲染器。
 *
 * 它不认识任何具体布局，只按布局数据把内容块摆到槽位里。
 * PPTX 渲染器做的是同一件事，两端因此天然一致：
 * 新增布局只需增加一份 JSON，两端都不用改代码。
 *
 * 编辑态复用同一棵渲染树：仅把可写字段换成受约束的 contenteditable。
 * flex 模式走 layout_tree solver，跳过固定布局装饰。
 */
export function SlideView({
  slide,
  theme,
  editable = false,
  selectedBlockId = null,
  onSelectBlock,
  onCommit,
}: SlideViewProps) {
  const flex = isFlexMode(slide)
  const layout = flex ? null : getLayout(slide.layout_id)
  const placements = flex
    ? new Map(solve(slide.layout_tree).map((p) => [p.block_id, p]))
    : null
  const skinDecorations = flex ? iterSkinDecorations(slide.layout_tree) : []

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
      {!flex &&
        layout!.decorations.map((decoration, index) => (
          <div
            key={`${decoration.type}-${index}`}
            aria-hidden
            style={{
              ...rectToStyle(decoration.rect),
              background: resolveColor(theme, decoration.color),
            }}
          />
        ))}

      {flex &&
        skinDecorations.map((decoration, index) => (
          <SkinDecorationView
            key={`skin-${decoration.kind}-${index}`}
            decoration={decoration}
            theme={theme}
          />
        ))}

      {slide.blocks.map((block) => {
        let rect: Rect
        let slot: Slot

        if (flex && placements) {
          const placed = placements.get(block.id)
          if (!placed) return null
          rect = placed.rect
          slot = flexPseudoSlot(block, placed)
        } else {
          const found = layout!.slots.find((candidate) => candidate.id === block.slot_id)
          if (!found) return null
          slot = found
          rect = found.rect
        }

        const selected = selectedBlockId === block.id
        const selectable = Boolean(editable)

        return (
          <div
            key={block.id}
            data-block-id={block.id}
            style={{
              ...rectToStyle(rect),
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

function SkinDecorationView({
  decoration,
  theme,
}: {
  decoration: SkinDecoration
  theme: Theme
}) {
  const color = resolveColor(theme, decoration.color_token)
  const base = rectToStyle(decoration.rect)

  if (decoration.kind === 'fill_box') {
    return (
      <div
        aria-hidden
        style={{
          ...base,
          background: color,
          borderRadius: pt(decoration.radius_pt ?? 0),
          zIndex: 0,
          pointerEvents: 'none',
        }}
      />
    )
  }

  if (decoration.kind === 'outline_box') {
    return (
      <div
        aria-hidden
        style={{
          ...base,
          border: `${pt(1.5)} solid ${color}`,
          borderRadius: pt(decoration.radius_pt ?? 0),
          boxSizing: 'border-box',
          zIndex: 0,
          pointerEvents: 'none',
        }}
      />
    )
  }

  if (decoration.kind === 'side_line' || decoration.kind === 'timeline_axis') {
    return (
      <div
        aria-hidden
        style={{
          ...base,
          background: color,
          zIndex: 0,
          pointerEvents: 'none',
        }}
      />
    )
  }

  if (decoration.kind === 'timeline_dot') {
    return (
      <div
        aria-hidden
        style={{
          ...base,
          background: color,
          borderRadius: '50%',
          zIndex: 0,
          pointerEvents: 'none',
        }}
      />
    )
  }

  // number_badge
  return (
    <div
      aria-hidden
      style={{
        ...base,
        background: color,
        borderRadius: '50%',
        display: 'grid',
        placeItems: 'center',
        color: resolveColor(theme, 'background'),
        fontSize: pt(11),
        fontWeight: 700,
        lineHeight: 1,
        zIndex: 0,
        pointerEvents: 'none',
      }}
    >
      {decoration.text}
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
