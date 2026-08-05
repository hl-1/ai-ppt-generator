from typing import Literal

from pydantic import BaseModel

from app.domain.content import Block, Deck, Slide
from app.domain.layout import Slot, get_layout

IssueSeverity = Literal["error", "warning"]


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
            StructureIssue(
                severity="warning", slide_id=slide_id, slot_id=slot.id, message=message
            )
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

    return issues


def validate_slide(slide: Slide) -> list[StructureIssue]:
    try:
        layout = get_layout(slide.layout_id)
    except KeyError as error:
        return [
            StructureIssue(
                severity="error", slide_id=slide.id, slot_id=None, message=str(error)
            )
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

        issues.extend(_capacity_issues(slide.id, slot, block))

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
    return [issue for slide in deck.slides for issue in validate_slide(slide)]


def has_blocking_issue(issues: list[StructureIssue]) -> bool:
    return any(issue.severity == "error" for issue in issues)
