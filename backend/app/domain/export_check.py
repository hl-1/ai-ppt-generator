"""导出前质量检查：分级报告与是否允许导出。

error 必须阻断导出；warning 可继续。检查逻辑独立成函数，
供质量报告接口与后续导出接口复用。
"""

from __future__ import annotations

import struct
from collections.abc import Callable, Mapping

from pydantic import BaseModel, Field

from app.domain.content import Deck, ImageBlock, Slide
from app.domain.geometry import CANVAS_HEIGHT_PT, CANVAS_WIDTH_PT
from app.domain.layout import get_layout
from app.domain.quality import check_deck_content_quality
from app.domain.theme import get_theme
from app.domain.validation import StructureIssue, has_blocking_issue, validate_deck

# 槽位内图片短边低于此像素视为分辨率偏低（96dpi × 约 1.5 英寸）
_LOW_RES_MIN_PX = 144


class ExportCheckReport(BaseModel):
    """导出前分级报告。"""

    issues: list[StructureIssue] = Field(default_factory=list)
    export_allowed: bool
    fonts_precise: bool = True


ImageLoader = Callable[[str], bytes]


def allow_export(issues: list[StructureIssue]) -> bool:
    """是否允许导出：存在任一 error 则否。"""
    return not has_blocking_issue(issues)


def check_slot_bounds(deck: Deck) -> list[StructureIssue]:
    """槽位矩形超出 16:9 画布边界 → error。"""
    issues: list[StructureIssue] = []
    for slide in deck.slides:
        try:
            layout = get_layout(slide.layout_id)
        except KeyError:
            continue
        for slot in layout.slots:
            right = slot.rect.x + slot.rect.w
            bottom = slot.rect.y + slot.rect.h
            if right > 1.0001 or bottom > 1.0001 or slot.rect.x < -1e-6 or slot.rect.y < -1e-6:
                issues.append(
                    StructureIssue(
                        severity="error",
                        slide_id=slide.id,
                        slot_id=slot.id,
                        message=(f"槽位超出 16:9 画布边界（右 {right:.3f} / 下 {bottom:.3f}）"),
                    )
                )
    return issues


def check_canvas_size(_deck: Deck) -> list[StructureIssue]:
    """页面尺寸异常：基准画布必须是 960×540 pt（16:9）。"""
    if abs(CANVAS_WIDTH_PT - 960.0) > 0.01 or abs(CANVAS_HEIGHT_PT - 540.0) > 0.01:
        return [
            StructureIssue(
                severity="error",
                slide_id="",
                slot_id=None,
                message=(
                    f"页面尺寸异常：当前基准为 {CANVAS_WIDTH_PT}×{CANVAS_HEIGHT_PT} pt，"
                    f"要求 960×540 pt（16:9）"
                ),
            )
        ]
    return []


def _image_size(data: bytes) -> tuple[int, int] | None:
    if data.startswith(b"\x89PNG\r\n\x1a\n") and len(data) >= 24:
        width, height = struct.unpack(">II", data[16:24])
        return int(width), int(height)
    if data.startswith(b"\xff\xd8\xff"):
        # 扫描 JPEG SOF
        offset = 2
        while offset + 9 < len(data):
            if data[offset] != 0xFF:
                break
            marker = data[offset + 1]
            if marker in {0xC0, 0xC1, 0xC2}:
                height, width = struct.unpack(">HH", data[offset + 5 : offset + 9])
                return int(width), int(height)
            if marker == 0xD9:
                break
            length = struct.unpack(">H", data[offset + 2 : offset + 4])[0]
            offset += 2 + length
        return None
    if len(data) >= 30 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        if data[12:16] == b"VP8 " and len(data) >= 30:
            width = struct.unpack("<H", data[26:28])[0] & 0x3FFF
            height = struct.unpack("<H", data[28:30])[0] & 0x3FFF
            return int(width), int(height)
        if data[12:16] == b"VP8L" and len(data) >= 25:
            bits = struct.unpack("<I", data[21:25])[0]
            width = (bits & 0x3FFF) + 1
            height = ((bits >> 14) & 0x3FFF) + 1
            return int(width), int(height)
    return None


def check_images(
    deck: Deck,
    *,
    load_image: ImageLoader | None,
    media_key_from_url: Callable[[str], str | None] | None,
) -> list[StructureIssue]:
    """图片资源不存在/无法读取 → error；分辨率偏低 → warning。"""
    if load_image is None or media_key_from_url is None:
        return []

    issues: list[StructureIssue] = []
    for slide in deck.slides:
        for block in slide.blocks:
            if not isinstance(block, ImageBlock):
                continue
            if block.source == "placeholder" or not block.url:
                continue
            key = media_key_from_url(block.url)
            if key is None:
                issues.append(
                    StructureIssue(
                        severity="error",
                        slide_id=slide.id,
                        slot_id=block.slot_id,
                        message="图片地址无效，无法在导出时读取",
                    )
                )
                continue
            try:
                data = load_image(key)
            except Exception:
                issues.append(
                    StructureIssue(
                        severity="error",
                        slide_id=slide.id,
                        slot_id=block.slot_id,
                        message="引用的图片资源不存在或无法读取",
                    )
                )
                continue
            if not data:
                issues.append(
                    StructureIssue(
                        severity="error",
                        slide_id=slide.id,
                        slot_id=block.slot_id,
                        message="引用的图片资源为空，无法导出",
                    )
                )
                continue

            size = _image_size(data)
            if size is None:
                issues.append(
                    StructureIssue(
                        severity="error",
                        slide_id=slide.id,
                        slot_id=block.slot_id,
                        message="图片无法解码，格式可能已损坏",
                    )
                )
                continue

            width_px, height_px = size
            if min(width_px, height_px) < _LOW_RES_MIN_PX:
                issues.append(
                    StructureIssue(
                        severity="warning",
                        slide_id=slide.id,
                        slot_id=block.slot_id,
                        message=(f"图片分辨率偏低（{width_px}×{height_px}），投影时可能发糊"),
                    )
                )
    return issues


def check_content_overflows_canvas(deck: Deck) -> list[StructureIssue]:
    """块内容渲染后必然溢出画布 → error。

    文字溢出槽位本身是 warning（由 validate 负责）；
    仅当「槽位顶边 + 实际占用高度」超出画布时升级为 error。
    """
    from app.domain.text_metrics import measure_bullets, measure_text
    from app.domain.theme import Theme

    try:
        theme: Theme = get_theme(deck.theme_id)
    except KeyError:
        return []

    issues: list[StructureIssue] = []
    for slide in deck.slides:
        try:
            layout = get_layout(slide.layout_id)
        except KeyError:
            continue
        for block in slide.blocks:
            slot = layout.slot_by_id(block.slot_id)
            if slot is None:
                continue
            _x, y_pt, w_pt, h_pt = slot.rect.to_points()
            used_height: float | None = None

            if block.type == "text":
                style = theme.text_style(slot.text_style or "body")
                used_height = measure_text(
                    block.text, style=style, width_pt=w_pt, height_pt=h_pt
                ).height_pt
            elif block.type == "bullets":
                style = theme.text_style(slot.text_style or "bullet")
                used_height = measure_bullets(
                    block.items, style=style, width_pt=w_pt, height_pt=h_pt
                ).height_pt

            if used_height is None:
                continue
            if y_pt + used_height > CANVAS_HEIGHT_PT + 0.5:
                issues.append(
                    StructureIssue(
                        severity="error",
                        slide_id=slide.id,
                        slot_id=slot.id,
                        message="内容渲染后将超出页面底边，请缩短文字或调整布局",
                    )
                )
    return issues


def check_font_metrics_availability() -> list[StructureIssue]:
    """度量字体缺失时提示：溢出检测为估算值（不阻断）。"""
    from app.domain.text_metrics import fonts_available

    if fonts_available():
        return []
    return [
        StructureIssue(
            severity="warning",
            slide_id="",
            slot_id=None,
            message=(
                "度量字体（Noto Sans / Noto Sans SC）未就绪，文字溢出检测使用估算值而非精确字形宽度"
            ),
        )
    ]


def run_export_check(
    deck: Deck,
    *,
    slide_titles: Mapping[str, str] | None = None,
    slide_sources: Mapping[str, str] | None = None,
    load_image: ImageLoader | None = None,
    media_key_from_url: Callable[[str], str | None] | None = None,
) -> ExportCheckReport:
    """产出导出前分级报告。"""
    from app.domain.text_metrics import fonts_available

    issues: list[StructureIssue] = []
    issues.extend(check_canvas_size(deck))
    issues.extend(validate_deck(deck))
    issues.extend(check_slot_bounds(deck))
    issues.extend(check_content_overflows_canvas(deck))
    issues.extend(check_images(deck, load_image=load_image, media_key_from_url=media_key_from_url))
    issues.extend(
        check_deck_content_quality(
            deck,
            slide_titles=slide_titles,
            slide_sources=slide_sources,
        )
    )
    issues.extend(check_font_metrics_availability())

    # 去重：同一 slide/slot/message 只保留一条
    deduped: list[StructureIssue] = []
    seen: set[tuple[str, str | None, str, str]] = set()
    for issue in issues:
        key = (issue.severity, issue.slide_id, issue.slot_id, issue.message)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(issue)

    return ExportCheckReport(
        issues=deduped,
        export_allowed=allow_export(deduped),
        fonts_precise=fonts_available(),
    )


def slide_to_deck_fragment(slide: Slide, *, deck_id: str, title: str, theme_id: str) -> Deck:
    """测试辅助：把单页包成 Deck。"""
    return Deck(id=deck_id, title=title, theme_id=theme_id, slides=[slide])
