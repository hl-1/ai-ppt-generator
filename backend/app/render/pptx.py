from io import BytesIO

from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR
from pptx.presentation import Presentation as PresentationType
from pptx.shapes.base import BaseShape
from pptx.slide import Slide as PptxSlide
from pptx.util import Emu, Pt

from app.domain.content import (
    Block,
    BulletsBlock,
    ChartBlock,
    Deck,
    ImageBlock,
    KpiBlock,
    Slide,
    TableBlock,
    TextBlock,
)
from app.domain.geometry import CANVAS_HEIGHT_PT, CANVAS_WIDTH_PT, EMU_PER_POINT, Rect
from app.domain.layout import Slot, get_layout
from app.domain.theme import Theme, get_theme
from app.render.color import mix, to_rgb
from app.render.table import set_cell_borders, use_plain_style
from app.render.text import apply_bullet, apply_text_style, write_paragraph

# 空白版式。用空白版式而非内置的标题版式，是因为槽位几何完全由我们的
# 布局数据决定，套用 PowerPoint 自带占位符反而会引入我们控制不了的位置。
BLANK_LAYOUT_INDEX = 6

BULLET_INDENT_PT = 18.0
BULLET_GAP_PT = 12.0


class PptxRenderer:
    """把统一内容模型渲染为 PPTX。

    它与 Web 渲染器读同一份布局与主题数据，做同一件事：
    按槽位摆放内容块。因此两端不会因为各自演进而排版分叉。

    所有输出都是 PowerPoint 原生对象（文本框、表格、形状），
    不含任何位图截图，保证导出结果可以直接编辑。
    """

    def __init__(self, theme: Theme) -> None:
        self.theme = theme

    def render(self, deck: Deck) -> BytesIO:
        presentation = Presentation()
        self._set_canvas(presentation)

        for slide in deck.slides:
            self._render_slide(presentation, slide)

        buffer = BytesIO()
        presentation.save(buffer)
        buffer.seek(0)
        return buffer

    def _set_canvas(self, presentation: PresentationType) -> None:
        presentation.slide_width = Pt(CANVAS_WIDTH_PT)
        presentation.slide_height = Pt(CANVAS_HEIGHT_PT)

    def _render_slide(self, presentation: PresentationType, slide: Slide) -> None:
        layout = get_layout(slide.layout_id)
        pptx_slide = presentation.slides.add_slide(presentation.slide_layouts[BLANK_LAYOUT_INDEX])

        self._fill_background(pptx_slide)

        for decoration in layout.decorations:
            self._add_filled_rect(pptx_slide, decoration.rect, self.theme.color(decoration.color))

        for block in slide.blocks:
            slot = layout.slot_by_id(block.slot_id)
            if slot is None:
                continue
            self._render_block(pptx_slide, slot, block)

        if slide.speaker_notes:
            pptx_slide.notes_slide.notes_text_frame.text = slide.speaker_notes

    def _fill_background(self, pptx_slide: PptxSlide) -> None:
        full_bleed = Rect(x=0, y=0, w=1, h=1)
        shape = self._add_filled_rect(pptx_slide, full_bleed, self.theme.palette.background)
        # 背景必须位于所有内容之下，新形状默认追加在末尾，因此显式前置
        pptx_slide.shapes._spTree.remove(shape._element)
        pptx_slide.shapes._spTree.insert(2, shape._element)

    def _add_filled_rect(
        self,
        pptx_slide: PptxSlide,
        rect: Rect,
        color: str,
        shape_type: MSO_SHAPE = MSO_SHAPE.RECTANGLE,
    ) -> BaseShape:
        left, top, width, height = (Emu(value) for value in rect.to_emu())
        shape = pptx_slide.shapes.add_shape(shape_type, left, top, width, height)
        shape.fill.solid()
        shape.fill.fore_color.rgb = to_rgb(color)
        shape.line.fill.background()
        shape.shadow.inherit = False
        return shape

    def _add_textbox(self, pptx_slide: PptxSlide, rect: Rect):
        left, top, width, height = (Emu(value) for value in rect.to_emu())
        textbox = pptx_slide.shapes.add_textbox(left, top, width, height)
        frame = textbox.text_frame
        frame.word_wrap = True
        frame.vertical_anchor = MSO_ANCHOR.TOP
        frame.margin_left = 0
        frame.margin_right = 0
        frame.margin_top = 0
        frame.margin_bottom = 0
        return frame

    def _render_block(self, pptx_slide: PptxSlide, slot: Slot, block: Block) -> None:
        match block:
            case TextBlock():
                self._render_text(pptx_slide, slot, block)
            case BulletsBlock():
                self._render_bullets(pptx_slide, slot, block)
            case KpiBlock():
                self._render_kpi(pptx_slide, slot, block)
            case TableBlock():
                self._render_table(pptx_slide, slot, block)
            case ImageBlock():
                self._render_image(pptx_slide, slot, block)
            case ChartBlock():
                self._render_chart(pptx_slide, slot, block)

    def _render_text(self, pptx_slide: PptxSlide, slot: Slot, block: TextBlock) -> None:
        style = self.theme.text_style(slot.text_style or "body")
        frame = self._add_textbox(pptx_slide, slot.rect)
        write_paragraph(frame.paragraphs[0], block.text, self.theme, style)

    def _render_bullets(self, pptx_slide: PptxSlide, slot: Slot, block: BulletsBlock) -> None:
        style = self.theme.text_style(slot.text_style or "bullet")
        frame = self._add_textbox(pptx_slide, slot.rect)

        for index, item in enumerate(block.items):
            paragraph = frame.paragraphs[0] if index == 0 else frame.add_paragraph()
            if index > 0:
                paragraph.space_before = Pt(BULLET_GAP_PT)
            write_paragraph(paragraph, item, self.theme, style)
            apply_bullet(paragraph, self.theme, BULLET_INDENT_PT)

    def _render_kpi(self, pptx_slide: PptxSlide, slot: Slot, block: KpiBlock) -> None:
        frame = self._add_textbox(pptx_slide, slot.rect)

        lines = [("kpi_value", block.value), ("kpi_label", block.label)]
        if block.note:
            lines.append(("kpi_note", block.note))

        for index, (style_name, content) in enumerate(lines):
            paragraph = frame.paragraphs[0] if index == 0 else frame.add_paragraph()
            if index > 0:
                paragraph.space_before = Pt(6)
            write_paragraph(paragraph, content, self.theme, self.theme.text_style(style_name))

    def _render_table(self, pptx_slide: PptxSlide, slot: Slot, block: TableBlock) -> None:
        left, top, width, height = (Emu(value) for value in slot.rect.to_emu())
        row_count = len(block.rows) + 1
        column_count = len(block.header)

        graphic_frame = pptx_slide.shapes.add_table(
            row_count, column_count, left, top, width, height
        )
        table = graphic_frame.table
        use_plain_style(table)

        header_style = self.theme.text_style("table_header")
        cell_style = self.theme.text_style("table_cell")
        header_rule = (1.5, self.theme.palette.accent)
        row_rule = (self.theme.shape.border_width_pt, self.theme.palette.line)

        for column_index, title in enumerate(block.header):
            self._write_cell(table.cell(0, column_index), title, header_style, header_rule)

        for row_index, row in enumerate(block.rows, start=1):
            for column_index, value in enumerate(row):
                self._write_cell(table.cell(row_index, column_index), value, cell_style, row_rule)

    def _write_cell(self, cell, content: str, style, bottom: tuple[float, str]) -> None:
        cell.fill.solid()
        cell.fill.fore_color.rgb = to_rgb(self.theme.palette.background)
        cell.margin_left = Pt(12)
        cell.margin_right = Pt(12)
        cell.margin_top = Pt(9)
        cell.margin_bottom = Pt(9)
        cell.vertical_anchor = MSO_ANCHOR.MIDDLE
        set_cell_borders(cell, bottom)

        paragraph = cell.text_frame.paragraphs[0]
        run = paragraph.add_run()
        run.text = content
        apply_text_style(run, self.theme, style)

    def _render_image(self, pptx_slide: PptxSlide, slot: Slot, block: ImageBlock) -> None:
        """图源缺失时用形状拼出与 Web 端同构的占位图形。

        刻意不生成位图：一旦插入图片，这块区域在 PowerPoint 里就不可编辑了，
        与"导出结果 100% 可编辑"的目标冲突。
        """
        rect = slot.rect
        accent = self.theme.palette.accent
        base = self.theme.palette.accent_soft

        self._add_filled_rect(pptx_slide, rect, base)

        outer = Rect(
            x=rect.x + rect.w * 0.44,
            y=rect.y + rect.h * 0.04,
            w=rect.w * 0.6,
            h=rect.h * 0.34,
        )
        inner = Rect(
            x=rect.x + rect.w * 0.56,
            y=rect.y + rect.h * 0.1,
            w=rect.w * 0.36,
            h=rect.h * 0.2,
        )
        self._add_filled_rect(pptx_slide, outer, mix(accent, base, 0.22), MSO_SHAPE.OVAL)
        self._add_filled_rect(pptx_slide, inner, mix(accent, base, 0.32), MSO_SHAPE.OVAL)
        self._add_placeholder_ridge(pptx_slide, rect, mix(accent, base, 0.16))

        rule = Rect(
            x=rect.x + rect.w * 0.08,
            y=rect.y + rect.h * 0.86,
            w=rect.w * 0.18,
            h=rect.h * 0.012,
        )
        self._add_filled_rect(pptx_slide, rule, accent)

    def _add_placeholder_ridge(self, pptx_slide: PptxSlide, rect: Rect, color: str) -> None:
        """占位图下半部的折线剪影，与 Web 端 SVG 用的是同一组顶点"""
        left, top, width, height = rect.to_points()

        def point(x: float, y: float) -> tuple[int, int]:
            return (
                Emu(round((left + width * x) * EMU_PER_POINT)),
                Emu(round((top + height * y) * EMU_PER_POINT)),
            )

        vertices = [(0.34, 0.52), (0.58, 0.7), (1.0, 0.4), (1.0, 1.0), (0.0, 1.0)]
        builder = pptx_slide.shapes.build_freeform(*point(0.0, 0.78))
        builder.add_line_segments([point(x, y) for x, y in vertices], close=True)

        shape = builder.convert_to_shape()
        shape.fill.solid()
        shape.fill.fore_color.rgb = to_rgb(color)
        shape.line.fill.background()
        shape.shadow.inherit = False

    def _render_chart(self, pptx_slide: PptxSlide, slot: Slot, block: ChartBlock) -> None:
        """原生图表在后续里程碑接入，此处先输出数据摘要文本框。

        与 Web 端保持同样的降级形态，避免两端在同一阶段呈现不一致。
        """
        style = self.theme.text_style("chart_label")
        frame = self._add_textbox(pptx_slide, slot.rect)
        frame.vertical_anchor = MSO_ANCHOR.MIDDLE

        unit = f" · 单位：{block.unit}" if block.unit else ""
        lines = [f"{block.chart_type} 图 · {' / '.join(block.categories)}{unit}"]
        lines += [
            f"{series.name}：{'、'.join(str(value) for value in series.values)}"
            for series in block.series
        ]

        for index, line in enumerate(lines):
            paragraph = frame.paragraphs[0] if index == 0 else frame.add_paragraph()
            if index > 0:
                paragraph.space_before = Pt(8)
            write_paragraph(paragraph, line, self.theme, style)


def render_deck_to_pptx(deck: Deck, theme_id: str | None = None) -> BytesIO:
    return PptxRenderer(get_theme(theme_id or deck.theme_id)).render(deck)
