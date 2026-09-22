from typing import Literal

from pydantic import BaseModel

from app.domain.content import (
    Block,
    CalloutBlock,
    CardsBlock,
    Deck,
    DiagramBlock,
    KpiBlock,
    Slide,
    TableBlock,
)
from app.domain.geometry import Rect
from app.domain.layout import Slot, get_layout
from app.domain.slide_geometry import placed_by_block_id
from app.domain.theme import Theme, get_theme

IssueSeverity = Literal["error", "warning"]

# 单页校验在缺少主题上下文时的回退；正式路径应传入项目主题
_DEFAULT_THEME_ID = "ivory"


def _resolve_theme(*, theme: Theme | None = None, theme_id: str | None = None) -> Theme:
    if theme is not None:
        return theme
    return get_theme(theme_id or _DEFAULT_THEME_ID)


class StructureIssue(BaseModel):
    """结构问题。

    error 表示内容与布局的契约被破坏，必须阻断导出；
    warning 表示内容偏长可能观感不佳，允许继续。
    code 用于生成 repair 分流：overflow/capacity 不触发砍块重写。
    """

    severity: IssueSeverity
    slide_id: str
    slot_id: str | None
    message: str
    code: str | None = None


def _capacity_issues(slide_id: str, slot: Slot, block: Block) -> list[StructureIssue]:
    capacity = slot.capacity
    issues: list[StructureIssue] = []

    def warn(message: str) -> None:
        issues.append(
            StructureIssue(
                severity="warning",
                slide_id=slide_id,
                slot_id=slot.id,
                message=message,
                code="capacity",
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

    if block.type == "cards":
        if capacity.max_items is not None and len(block.items) > capacity.max_items:
            warn(f"卡片 {len(block.items)} 张，超出建议上限 {capacity.max_items} 张")
        if capacity.max_chars_per_item is not None:
            for index, item in enumerate(block.items):
                total = len(item.title) + len(item.desc)
                if total > capacity.max_chars_per_item:
                    warn(
                        f"第 {index + 1} 张卡片 {total} 字，"
                        f"超出单卡上限 {capacity.max_chars_per_item} 字"
                    )

    if block.type == "callout" and capacity.max_chars is not None:
        if len(block.text) > capacity.max_chars:
            warn(f"提示条 {len(block.text)} 字，超出建议上限 {capacity.max_chars} 字")

    if block.type == "table":
        if capacity.max_columns is not None and len(block.header) > capacity.max_columns:
            warn(f"表格 {len(block.header)} 列，超出上限 {capacity.max_columns} 列")
        if capacity.max_rows is not None and len(block.rows) > capacity.max_rows:
            warn(f"表格 {len(block.rows)} 行，超出上限 {capacity.max_rows} 行")
        if capacity.max_chars_per_cell is not None:
            for row_index, row in enumerate([block.header, *block.rows]):
                for column_index, cell in enumerate(row):
                    if len(cell) > capacity.max_chars_per_cell:
                        warn(
                            f"表格第 {row_index + 1} 行第 {column_index + 1} 列 "
                            f"{len(cell)} 字，超出单元格上限 {capacity.max_chars_per_cell} 字"
                        )

    if block.type == "chart":
        if capacity.max_series is not None and len(block.series) > capacity.max_series:
            warn(f"图表 {len(block.series)} 条系列，超出上限 {capacity.max_series} 条")
        if capacity.max_categories is not None and len(block.categories) > capacity.max_categories:
            warn(f"图表 {len(block.categories)} 个分类，超出上限 {capacity.max_categories} 个")

    if block.type == "diagram":
        if capacity.max_items is not None and len(block.nodes) > capacity.max_items:
            warn(f"结构图 {len(block.nodes)} 个节点，超出建议上限 {capacity.max_items} 个")
        if capacity.max_chars_per_item is not None:
            for index, node in enumerate(block.nodes):
                total = len(node.title) + len(node.desc)
                if total > capacity.max_chars_per_item:
                    warn(
                        f"第 {index + 1} 个节点 {total} 字，"
                        f"超出单节点上限 {capacity.max_chars_per_item} 字"
                    )

    return issues


def _overflow_issues(
    slide_id: str,
    block: Block,
    *,
    rect: Rect,
    text_style: str | None,
    theme: Theme,
    ref_id: str | None = None,
) -> list[StructureIssue]:
    """基于字体度量检测所有块的内容边界；warning，不直接阻断导出。"""
    measurements = _measure_block_overflow(block, rect=rect, text_style=text_style, theme=theme)
    issues: list[StructureIssue] = []
    for label, used_height, available_height, line_count, used_estimate in measurements:
        if used_height <= available_height + 0.5:
            continue
        estimate_note = "（估算值）" if used_estimate else ""
        issues.append(
            StructureIssue(
                severity="warning",
                slide_id=slide_id,
                slot_id=ref_id,
                message=(
                    f"{label}可能溢出槽位{estimate_note}："
                    f"约需 {line_count} 行"
                    f"（占用 {used_height:.0f} pt / 槽位 {available_height:.0f} pt）"
                ),
                code="overflow",
            )
        )
    return issues


def _measure_block_overflow(
    block: Block,
    *,
    rect: Rect,
    text_style: str | None,
    theme: Theme,
) -> list[tuple[str, float, float, int, bool]]:
    """返回（标签、实际高度、可用高度、行数、是否估算）。"""
    from app.domain.block_style import content_rect_pt, merge_text_style, resolve_box
    from app.domain.text_metrics import measure_bullets, measure_text

    _x, _y, width_pt, height_pt = rect.to_points()
    box = resolve_box(theme, block.style)
    avail_w, avail_h = content_rect_pt(width_pt, height_pt, padding_pt=box.padding_pt)
    results: list[tuple[str, float, float, int, bool]] = []

    if block.type == "text":
        style = merge_text_style(theme, text_style or "body", block.style)
        result = measure_text(block.text, style=style, width_pt=avail_w, height_pt=avail_h)
        results.append(("文字", result.height_pt, avail_h, result.line_count, result.used_estimate))
        return results

    if block.type == "bullets":
        style = merge_text_style(theme, text_style or "bullet", block.style)
        result = measure_bullets(block.items, style=style, width_pt=avail_w, height_pt=avail_h)
        results.append(("要点", result.height_pt, avail_h, result.line_count, result.used_estimate))
        return results

    if isinstance(block, CardsBlock):
        results.extend(_measure_cards(block, width_pt=avail_w, height_pt=avail_h, theme=theme))
        return results

    if isinstance(block, TableBlock):
        results.extend(_measure_table(block, width_pt=avail_w, height_pt=avail_h, theme=theme))
        return results

    if isinstance(block, DiagramBlock):
        results.extend(_measure_diagram(block, width_pt=avail_w, height_pt=avail_h, theme=theme))
        return results

    if isinstance(block, CalloutBlock):
        style_name = "caption" if block.variant == "source" else "body"
        style = merge_text_style(theme, style_name, block.style)
        text = f"{block.icon} {block.text}".strip() if block.icon else block.text
        result = measure_text(
            text,
            style=style,
            width_pt=max(1.0, avail_w - 8.0),
            height_pt=avail_h,
        )
        results.append(
            ("提示条", result.height_pt, avail_h, result.line_count, result.used_estimate)
        )
        return results

    if isinstance(block, KpiBlock):
        results.extend(_measure_kpi(block, width_pt=avail_w, height_pt=avail_h, theme=theme))
        return results

    return results


def _measure_cards(
    block: CardsBlock,
    *,
    width_pt: float,
    height_pt: float,
    theme: Theme,
) -> list[tuple[str, float, float, int, bool]]:
    from app.domain.block_style import merge_text_style
    from app.domain.text_metrics import measure_text

    if not block.items:
        return []
    gap = 16.0
    pad = 12.0
    min_width = 96.0
    columns = min(
        len(block.items),
        max(1, int((width_pt + gap) // (min_width + gap))),
    )
    rows = (len(block.items) + columns - 1) // columns
    card_w = max((width_pt - gap * max(columns - 1, 0)) / columns, 1.0)
    card_h = max((height_pt - gap * max(rows - 1, 0)) / rows, 1.0)
    inner_w = max(card_w - 2 * pad, 1.0)
    inner_h = max(card_h - 2 * pad, 1.0)
    title_style = merge_text_style(theme, "subtitle", block.style)
    body_style = merge_text_style(theme, "body", block.style)
    results = []
    for index, item in enumerate(block.items):
        title = f"{item.icon} {item.title}".strip() if item.icon else item.title
        title_result = measure_text(
            title, style=title_style, width_pt=inner_w, height_pt=inner_h
        )
        desc_result = measure_text(
            item.desc, style=body_style, width_pt=inner_w, height_pt=inner_h
        )
        used = title_result.height_pt + 6.0 + desc_result.height_pt
        results.append(
            (
                f"第 {index + 1} 张卡片",
                used,
                inner_h,
                title_result.line_count + desc_result.line_count,
                title_result.used_estimate or desc_result.used_estimate,
            )
        )
    return results


def _measure_table(
    block: TableBlock,
    *,
    width_pt: float,
    height_pt: float,
    theme: Theme,
) -> list[tuple[str, float, float, int, bool]]:
    from app.domain.block_style import merge_text_style
    from app.domain.text_metrics import measure_text

    columns = max(len(block.header), 1)
    row_count = len(block.rows) + 1
    cell_w = max(width_pt / columns - 24.0, 1.0)
    cell_h = max(height_pt / row_count - 18.0, 1.0)
    header_style = merge_text_style(theme, "table_header", block.style)
    cell_style = merge_text_style(theme, "table_cell", block.style)
    results = []
    all_rows = [block.header, *block.rows]
    for row_index, row in enumerate(all_rows):
        style = header_style if row_index == 0 else cell_style
        for column_index, value in enumerate(row[:columns]):
            result = measure_text(value, style=style, width_pt=cell_w, height_pt=cell_h)
            results.append(
                (
                    f"表格第 {row_index + 1} 行第 {column_index + 1} 列",
                    result.height_pt,
                    cell_h,
                    result.line_count,
                    result.used_estimate,
                )
            )
    return results


def _measure_diagram(
    block: DiagramBlock,
    *,
    width_pt: float,
    height_pt: float,
    theme: Theme,
) -> list[tuple[str, float, float, int, bool]]:
    from app.domain.block_style import merge_text_style
    from app.domain.text_metrics import measure_text

    count = len(block.nodes)
    if count == 0:
        return []
    gap_x = 18.0
    gap_y = 16.0
    if block.diagram_type == "timeline":
        node_h = max((height_pt - gap_y * (count - 1)) / count, 1.0)
        node_w = width_pt * 0.82
        geometry_height = node_h * count + gap_y * (count - 1)
    else:
        node_w = max((width_pt - gap_x * (count - 1)) / count, 120.0)
        node_h = height_pt * 0.64
        geometry_height = node_h
    inner_w = max(node_w - 24.0, 1.0)
    inner_h = max(node_h - 24.0, 1.0)
    title_style = merge_text_style(theme, "subtitle", block.style)
    body_style = merge_text_style(theme, "body", block.style)
    results = []
    if geometry_height > height_pt + 0.5 or (
        block.diagram_type != "timeline"
        and node_w * count + gap_x * (count - 1) > width_pt + 0.5
    ):
        results.append(("结构图节点区域", geometry_height, height_pt, count, False))
    for index, node in enumerate(block.nodes):
        title_result = measure_text(
            node.title, style=title_style, width_pt=inner_w, height_pt=inner_h
        )
        desc_result = measure_text(
            node.desc, style=body_style, width_pt=inner_w, height_pt=inner_h
        ) if node.desc else None
        used = title_result.height_pt + (6.0 + desc_result.height_pt if desc_result else 0.0)
        results.append(
            (
                f"第 {index + 1} 个结构图节点",
                used,
                inner_h,
                title_result.line_count + (desc_result.line_count if desc_result else 0),
                title_result.used_estimate or (desc_result.used_estimate if desc_result else False),
            )
        )
    return results


def _measure_kpi(
    block: KpiBlock,
    *,
    width_pt: float,
    height_pt: float,
    theme: Theme,
) -> list[tuple[str, float, float, int, bool]]:
    from app.domain.text_metrics import measure_text

    lines = [
        ("指标数值", "kpi_value", block.value),
        ("指标标签", "kpi_label", block.label),
    ]
    if block.note:
        lines.append(("指标备注", "kpi_note", block.note))
    used = 0.0
    count = 0
    estimated = False
    for index, (_label, style_name, text) in enumerate(lines):
        style = theme.text_style(style_name) if block.style is None else None
        if style is None:
            from app.domain.block_style import merge_text_style

            style = merge_text_style(theme, style_name, block.style)
        result = measure_text(text, style=style, width_pt=width_pt, height_pt=height_pt)
        used += result.height_pt
        if index:
            used += 8.0
        count += result.line_count
        estimated = estimated or result.used_estimate
    return [("KPI 内容", used, height_pt, count, estimated)]


def _geometry_issues(
    slide: Slide,
    *,
    placed: dict[str, object],
    blocks: list[Block],
) -> list[StructureIssue]:
    """检查所有内容块的矩形边界与明显碰撞。"""
    issues: list[StructureIssue] = []
    by_id = {block.id: block for block in blocks}
    entries = [(block_id, entry) for block_id, entry in placed.items() if block_id in by_id]
    for block_id, entry in entries:
        rect = entry.rect  # type: ignore[attr-defined]
        right = rect.x + rect.w
        bottom = rect.y + rect.h
        if rect.x < -1e-6 or rect.y < -1e-6 or right > 1.0001 or bottom > 1.0001:
            issues.append(
                StructureIssue(
                    severity="error",
                    slide_id=slide.id,
                    slot_id=block_id,
                    message=f"内容块超出 16:9 画布边界（右 {right:.3f} / 下 {bottom:.3f}）",
                    code="bounds",
                )
            )

    for index, (left_id, left_entry) in enumerate(entries):
        left = left_entry.rect  # type: ignore[attr-defined]
        left_area = left.w * left.h
        for right_id, right_entry in entries[index + 1 :]:
            right = right_entry.rect  # type: ignore[attr-defined]
            overlap_w = max(0.0, min(left.right, right.right) - max(left.x, right.x))
            overlap_h = max(0.0, min(left.bottom, right.bottom) - max(left.y, right.y))
            overlap = overlap_w * overlap_h
            if overlap <= 0 or overlap <= 0.15 * min(left_area, right.w * right.h):
                continue
            issues.append(
                StructureIssue(
                    severity="error",
                    slide_id=slide.id,
                    slot_id=right_id,
                    message=f"内容块 {left_id} 与 {right_id} 的区域明显重叠，请调整布局",
                    code="block_overlap",
                )
            )
    return issues


def _validate_fixed_slide(
    slide: Slide, *, theme: Theme
) -> list[StructureIssue]:
    try:
        layout = get_layout(slide.layout_id)
    except KeyError as error:
        return [
            StructureIssue(severity="error", slide_id=slide.id, slot_id=None, message=str(error))
        ]

    issues: list[StructureIssue] = []
    seen: set[str] = set()
    placed = placed_by_block_id(slide)

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

        # 字数上限约束提示词；度量溢出作为更准确的一层 warning
        issues.extend(_capacity_issues(slide.id, slot, block))
        placement = placed.get(block.id)
        if placement is not None:
            issues.extend(
                _overflow_issues(
                    slide.id,
                    block,
                    rect=placement.rect,
                    text_style=placement.text_style,
                    theme=theme,
                    ref_id=slot.id,
                )
            )

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

    issues.extend(_geometry_issues(slide, placed=placed, blocks=slide.blocks))
    return issues


def _validate_flex_slide(slide: Slide, *, theme: Theme) -> list[StructureIssue]:
    from app.domain.flex_layout import iter_leaf_block_ids

    issues: list[StructureIssue] = []
    if slide.layout_tree is None:
        return [
            StructureIssue(
                severity="error",
                slide_id=slide.id,
                slot_id=None,
                message="灵活布局缺少 layout_tree",
            )
        ]

    block_by_id = {block.id: block for block in slide.blocks}
    leaf_ids = iter_leaf_block_ids(slide.layout_tree)
    for block_id in leaf_ids:
        if block_id not in block_by_id:
            issues.append(
                StructureIssue(
                    severity="error",
                    slide_id=slide.id,
                    slot_id=block_id,
                    message=f"布局树引用了不存在的内容块 {block_id}",
                )
            )

    try:
        placed = placed_by_block_id(slide)
    except Exception as error:
        return issues + [
            StructureIssue(
                severity="error",
                slide_id=slide.id,
                slot_id=None,
                message=f"灵活布局求解失败：{error}",
            )
        ]

    for block in slide.blocks:
        placement = placed.get(block.id)
        if placement is None:
            issues.append(
                StructureIssue(
                    severity="error",
                    slide_id=slide.id,
                    slot_id=block.slot_id or block.id,
                    message=f"内容块 {block.id} 在布局树中没有几何位置",
                )
            )
            continue
        # flex 无槽位 capacity，跳过容量检查；仍做溢出度量
        issues.extend(
            _overflow_issues(
                slide.id,
                block,
                rect=placement.rect,
                text_style=placement.text_style,
                theme=theme,
                ref_id=block.slot_id or block.id,
            )
        )

    issues.extend(_geometry_issues(slide, placed=placed, blocks=slide.blocks))
    return issues


def validate_slide(
    slide: Slide,
    *,
    theme_id: str | None = None,
    theme: Theme | None = None,
) -> list[StructureIssue]:
    try:
        resolved_theme = _resolve_theme(theme=theme, theme_id=theme_id)
    except KeyError as error:
        return [
            StructureIssue(severity="error", slide_id=slide.id, slot_id=None, message=str(error))
        ]

    if slide.layout_mode == "flex":
        return _validate_flex_slide(slide, theme=resolved_theme)
    return _validate_fixed_slide(slide, theme=resolved_theme)


def validate_deck(deck: Deck, *, theme: Theme | None = None) -> list[StructureIssue]:
    resolved = theme
    if resolved is None:
        try:
            resolved = get_theme(deck.theme_id)
        except KeyError:
            resolved = get_theme(_DEFAULT_THEME_ID)
    return [issue for slide in deck.slides for issue in validate_slide(slide, theme=resolved)]


def has_blocking_issue(issues: list[StructureIssue]) -> bool:
    return any(issue.severity == "error" for issue in issues)
