from typing import Literal

from pydantic import BaseModel

from app.domain.content import Block, Deck, Slide
from app.domain.layout import Slot, get_layout
from app.domain.theme import get_theme

IssueSeverity = Literal["error", "warning"]

# 单页校验在缺少主题上下文时的回退；正式路径应传入项目 theme_id
_DEFAULT_THEME_ID = "ivory"


class StructureIssue(BaseModel):
    """结构问题。

    error 表示内容与布局的契约被破坏，必须阻断导出；
    warning 表示内容偏长可能观感不佳，允许继续。
    """

    severity: IssueSeverity
    slide_id: str
    slot_id: str | None
    message: str


def _capacity_issues(slide_id: str, slot: Slot, block: Block) -> list[StructureIssue]:
    capacity = slot.capacity
    issues: list[StructureIssue] = []

    def warn(message: str) -> None:
        issues.append(
            StructureIssue(severity="warning", slide_id=slide_id, slot_id=slot.id, message=message)
        )

    if block.type == "text" and capacity.max_chars is not None:
        if len(block.text) > capacity.max_chars:
            warn(f"文字 {len(block.text)} 字，超出建议上限 {capacity.max_chars} 字")

    if block.type == "bullets":
        if capacity.max_items is not None and len(block.items) > capacity.max_items:
            warn(f"要点 {len(block.items)} 条，超出建议上限 {capacity.max_items} 条")
        if capacity.max_chars_per_item is not None:
            for index, item in enumerate(block.items):
                if len(item) > capacity.max_chars_per_item:
                    warn(
                        f"第 {index + 1} 条要点 {len(item)} 字，"
                        f"超出单条上限 {capacity.max_chars_per_item} 字"
                    )

    if block.type == "table":
        if capacity.max_columns is not None and len(block.header) > capacity.max_columns:
            warn(f"表格 {len(block.header)} 列，超出上限 {capacity.max_columns} 列")
        if capacity.max_rows is not None and len(block.rows) > capacity.max_rows:
            warn(f"表格 {len(block.rows)} 行，超出上限 {capacity.max_rows} 行")

    if block.type == "chart":
        if capacity.max_series is not None and len(block.series) > capacity.max_series:
            warn(f"图表 {len(block.series)} 条系列，超出上限 {capacity.max_series} 条")
        if capacity.max_categories is not None and len(block.categories) > capacity.max_categories:
            warn(f"图表 {len(block.categories)} 个分类，超出上限 {capacity.max_categories} 个")

    return issues


def _overflow_issues(
    slide_id: str, slot: Slot, block: Block, *, theme_id: str
) -> list[StructureIssue]:
    """基于字体度量的文字溢出检测；warning，不阻断。"""
    if block.type not in {"text", "bullets"}:
        return []
    if slot.text_style is None:
        return []

    from app.domain.text_metrics import measure_bullets, measure_text

    try:
        theme = get_theme(theme_id)
    except KeyError:
        return []

    _x, _y, width_pt, height_pt = slot.rect.to_points()
    if block.type == "text":
        style = theme.text_style(slot.text_style or "body")
        result = measure_text(block.text, style=style, width_pt=width_pt, height_pt=height_pt)
        label = "文字"
    else:
        style = theme.text_style(slot.text_style or "bullet")
        result = measure_bullets(block.items, style=style, width_pt=width_pt, height_pt=height_pt)
        label = "要点"

    if not result.overflows:
        return []

    estimate_note = "（估算值）" if result.used_estimate else ""
    return [
        StructureIssue(
            severity="warning",
            slide_id=slide_id,
            slot_id=slot.id,
            message=(
                f"{label}可能溢出槽位{estimate_note}："
                f"约需 {result.line_count} 行"
                f"（占用 {result.height_pt:.0f} pt / 槽位 {height_pt:.0f} pt）"
            ),
        )
    ]


def validate_slide(slide: Slide, *, theme_id: str | None = None) -> list[StructureIssue]:
    resolved_theme = theme_id or _DEFAULT_THEME_ID
    try:
        layout = get_layout(slide.layout_id)
    except KeyError as error:
        return [
            StructureIssue(severity="error", slide_id=slide.id, slot_id=None, message=str(error))
        ]

    issues: list[StructureIssue] = []
    seen: set[str] = set()

    for block in slide.blocks:
        slot = layout.slot_by_id(block.slot_id)
        if slot is None:
            issues.append(
                StructureIssue(
                    severity="error",
                    slide_id=slide.id,
                    slot_id=block.slot_id,
                    message=f"布局 {layout.id} 不存在该槽位",
                )
            )
            continue

        if block.slot_id in seen:
            issues.append(
                StructureIssue(
                    severity="error",
                    slide_id=slide.id,
                    slot_id=slot.id,
                    message="同一槽位被多个内容块占用",
                )
            )
        seen.add(block.slot_id)

        if block.type not in slot.accepts:
            issues.append(
                StructureIssue(
                    severity="error",
                    slide_id=slide.id,
                    slot_id=slot.id,
                    message=f"槽位只接受 {'、'.join(slot.accepts)}，实际为 {block.type}",
                )
            )
            continue

        # 字数上限是提示词约束依据，保留；度量溢出是更准的一层 warning
        issues.extend(_capacity_issues(slide.id, slot, block))
        issues.extend(_overflow_issues(slide.id, slot, block, theme_id=resolved_theme))

    for slot in layout.slots:
        if slot.required and slot.id not in seen:
            issues.append(
                StructureIssue(
                    severity="error",
                    slide_id=slide.id,
                    slot_id=slot.id,
                    message="必填槽位缺少内容",
                )
            )

    return issues


def validate_deck(deck: Deck) -> list[StructureIssue]:
    return [
        issue for slide in deck.slides for issue in validate_slide(slide, theme_id=deck.theme_id)
    ]


def has_blocking_issue(issues: list[StructureIssue]) -> bool:
    return any(issue.severity == "error" for issue in issues)
