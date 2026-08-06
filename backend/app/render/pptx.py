import logging
from io import BytesIO

from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.parts.image import Image as PptxImage
from pptx.presentation import Presentation as PresentationType
from pptx.shapes.base import BaseShape
from pptx.slide import Slide as PptxSlide
from pptx.util import Emu, Pt

from app.domain.block_style import BlockStyle, ResolvedBox, merge_text_style, resolve_box
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
from app.render.chart import render_chart
from app.render.color import mix, to_rgb
from app.render.table import set_cell_borders, use_plain_style
from app.render.text import apply_bullet, apply_text_style, write_paragraph
from app.services.media import load_image, media_key_from_url

logger = logging.getLogger(__name__)

# 空白版式。用空白版式而非内置的标题版式，是因为槽位几何完全由我们的
# 布局数据决定，套用 PowerPoint 自带占位符反而会引入我们控制不了的位置。
BLANK_LAYOUT_INDEX = 6

BULLET_INDENT_PT = 18.0
BULLET_GAP_PT = 12.0

_ALIGN = {
    "left": PP_ALIGN.LEFT,
    "center": PP_ALIGN.CENTER,
    "right": PP_ALIGN.RIGHT,
}


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
        *,
        radius_pt: float = 0,
        border_width_pt: float = 0,
        border_color: str | None = None,
    ) -> BaseShape:
        left, top, width, height = (Emu(value) for value in rect.to_emu())
        shape = pptx_slide.shapes.add_shape(shape_type, left, top, width, height)
        shape.fill.solid()
        shape.fill.fore_color.rgb = to_rgb(color)
        if border_width_pt > 0 and border_color is not None:
            shape.line.color.rgb = to_rgb(border_color)
            shape.line.width = Pt(border_width_pt)
        else:
            shape.line.fill.background()
        shape.shadow.inherit = False
        if shape_type == MSO_SHAPE.ROUNDED_RECTANGLE and radius_pt > 0:
            # adjustments[0] 是相对短边的圆角比例，夹在 0–0.5
            short_side = min(rect.w * CANVAS_WIDTH_PT, rect.h * CANVAS_HEIGHT_PT)
            if short_side > 0:
                shape.adjustments[0] = min(0.5, max(0.0, radius_pt / short_side))
        return shape

    def _add_box_chrome(self, pptx_slide: PptxSlide, rect: Rect, box: ResolvedBox) -> None:
        if not box.has_chrome and box.radius_pt <= 0:
            return
        if not box.has_fill and not box.has_border:
            return
        shape_type = (
            MSO_SHAPE.ROUNDED_RECTANGLE if box.radius_pt > 0 else MSO_SHAPE.RECTANGLE
        )
        fill = box.fill or self.theme.palette.background
        # 无填充但有边框时用背景色铺底再画线，避免透明形状在部分客户端丢边框
        if box.has_fill:
            color = fill
        else:
            # 透明填充 + 边框
            left, top, width, height = (Emu(value) for value in rect.to_emu())
            shape = pptx_slide.shapes.add_shape(shape_type, left, top, width, height)
            shape.fill.background()
            if box.has_border:
                shape.line.color.rgb = to_rgb(box.border_color)  # type: ignore[arg-type]
                shape.line.width = Pt(box.border_width_pt)
            else:
                shape.line.fill.background()
            shape.shadow.inherit = False
            if shape_type == MSO_SHAPE.ROUNDED_RECTANGLE and box.radius_pt > 0:
                short_side = min(rect.w * CANVAS_WIDTH_PT, rect.h * CANVAS_HEIGHT_PT)
                if short_side > 0:
                    shape.adjustments[0] = min(0.5, max(0.0, box.radius_pt / short_side))
            return

        self._add_filled_rect(
            pptx_slide,
            rect,
            color,
            shape_type,
            radius_pt=box.radius_pt,
            border_width_pt=box.border_width_pt,
            border_color=box.border_color,
        )

    def _padded_rect(self, rect: Rect, padding_pt: float) -> Rect:
        if padding_pt <= 0:
            return rect
        pad_x = padding_pt / CANVAS_WIDTH_PT
        pad_y = padding_pt / CANVAS_HEIGHT_PT
        # 内缩后仍保底一点尺寸，避免极端 padding 把文本框压成零
        w = max(0.01, rect.w - pad_x * 2)
        h = max(0.01, rect.h - pad_y * 2)
        return Rect(x=rect.x + pad_x, y=rect.y + pad_y, w=w, h=h)

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

    def _apply_align(self, paragraph, align: str | None) -> None:
        if align is None:
            return
        paragraph.alignment = _ALIGN.get(align)

    def _styled_textbox(
        self,
        pptx_slide: PptxSlide,
        slot: Slot,
        style: BlockStyle | None,
    ):
        box = resolve_box(self.theme, style)
        self._add_box_chrome(pptx_slide, slot.rect, box)
        content_rect = self._padded_rect(slot.rect, box.padding_pt)
        return self._add_textbox(pptx_slide, content_rect), style.align if style else None

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
        style = merge_text_style(self.theme, slot.text_style or "body", block.style)
        frame, align = self._styled_textbox(pptx_slide, slot, block.style)
        paragraph = frame.paragraphs[0]
        write_paragraph(paragraph, block.text, self.theme, style)
        self._apply_align(paragraph, align)

    def _render_bullets(self, pptx_slide: PptxSlide, slot: Slot, block: BulletsBlock) -> None:
        style = merge_text_style(self.theme, slot.text_style or "bullet", block.style)
        frame, align = self._styled_textbox(pptx_slide, slot, block.style)

        for index, item in enumerate(block.items):
            paragraph = frame.paragraphs[0] if index == 0 else frame.add_paragraph()
            if index > 0:
                paragraph.space_before = Pt(BULLET_GAP_PT)
            write_paragraph(paragraph, item, self.theme, style)
            apply_bullet(paragraph, self.theme, BULLET_INDENT_PT)
            self._apply_align(paragraph, align)

    def _render_kpi(self, pptx_slide: PptxSlide, slot: Slot, block: KpiBlock) -> None:
        frame, align = self._styled_textbox(pptx_slide, slot, block.style)

        lines = [("kpi_value", block.value), ("kpi_label", block.label)]
        if block.note:
            lines.append(("kpi_note", block.note))

        for index, (style_name, content) in enumerate(lines):
            paragraph = frame.paragraphs[0] if index == 0 else frame.add_paragraph()
            if index > 0:
                paragraph.space_before = Pt(6)
            # KPI 各行共用同一份元素覆盖（字号/颜色/粗斜体）
            text_style = merge_text_style(self.theme, style_name, block.style)
            write_paragraph(paragraph, content, self.theme, text_style)
            self._apply_align(paragraph, align)

    def _render_table(self, pptx_slide: PptxSlide, slot: Slot, block: TableBlock) -> None:
        left, top, width, height = (Emu(value) for value in slot.rect.to_emu())
        row_count = len(block.rows) + 1
        column_count = len(block.header)

        graphic_frame = pptx_slide.shapes.add_table(
            row_count, column_count, left, top, width, height
        )
        table = graphic_frame.table
        use_plain_style(table)

        header_style = merge_text_style(self.theme, "table_header", block.style)
        cell_style = merge_text_style(self.theme, "table_cell", block.style)
        header_rule = (1.5, self.theme.palette.accent)
        row_rule = (self.theme.shape.border_width_pt, self.theme.palette.line)
        align = block.style.align if block.style else None

        for column_index, title in enumerate(block.header):
            self._write_cell(
                table.cell(0, column_index), title, header_style, header_rule, align=align
            )

        for row_index, row in enumerate(block.rows, start=1):
            for column_index, value in enumerate(row):
                self._write_cell(
                    table.cell(row_index, column_index),
                    value,
                    cell_style,
                    row_rule,
                    align=align,
                )

    def _write_cell(
        self,
        cell,
        content: str,
        style,
        bottom: tuple[float, str],
        *,
        align: str | None = None,
    ) -> None:
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
        self._apply_align(paragraph, align)

    def _apply_image_border(self, picture, style: BlockStyle | None) -> None:
        box = resolve_box(self.theme, style)
        if not box.has_border:
            return
        picture.line.color.rgb = to_rgb(box.border_color)  # type: ignore[arg-type]
        picture.line.width = Pt(box.border_width_pt)

    def _render_image(self, pptx_slide: PptxSlide, slot: Slot, block: ImageBlock) -> None:
        """插入真实图片，或在缺失时用形状拼出与 Web 端同构的占位图形。

        真实图片本来就是位图对象，插入后在 PowerPoint 里仍可选中、移动和替换；
        只有占位图用形状拼，避免把"没有图"这件事固化成一张不可编辑的图。
        """
        if block.url:
            key = media_key_from_url(block.url)
            if key is not None:
                try:
                    picture = self._add_cover_picture(pptx_slide, slot.rect, load_image(key))
                    self._apply_image_border(picture, block.style)
                    return
                except Exception as error:
                    logger.warning("图片读取或解码失败，回退占位图：key=%s error=%s", key, error)

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
        # 占位图用外层 chrome 画边框
        box = resolve_box(self.theme, block.style)
        if box.has_border:
            self._add_box_chrome(
                pptx_slide,
                rect,
                ResolvedBox(
                    fill=None,
                    radius_pt=0,
                    border_width_pt=box.border_width_pt,
                    border_color=box.border_color,
                    padding_pt=0,
                ),
            )

    def _add_cover_picture(self, pptx_slide: PptxSlide, rect: Rect, data: bytes):
        """覆盖式裁切，等价于 CSS object-fit: cover，两端观感才一致。"""
        left_pt, top_pt, width_pt, height_pt = rect.to_points()
        left, top, width, height = (Pt(value) for value in (left_pt, top_pt, width_pt, height_pt))
        px_w, px_h = PptxImage.from_blob(data).size
        slot_ratio = width_pt / height_pt
        img_ratio = px_w / px_h

        picture = pptx_slide.shapes.add_picture(BytesIO(data), left, top, width, height)
        if img_ratio > slot_ratio:
            crop = (1 - slot_ratio / img_ratio) / 2
            picture.crop_left = crop
            picture.crop_right = crop
        else:
            crop = (1 - img_ratio / slot_ratio) / 2
            picture.crop_top = crop
            picture.crop_bottom = crop
        return picture

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
        render_chart(pptx_slide, slot.rect, block, self.theme)


def render_deck_to_pptx(
    deck: Deck,
    theme_id: str | None = None,
    *,
    theme: Theme | None = None,
) -> BytesIO:
    resolved = theme or get_theme(theme_id or deck.theme_id)
    return PptxRenderer(resolved).render(deck)
