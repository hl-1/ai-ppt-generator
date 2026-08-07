"""将 FlexContainer 树递归求解为归一化矩形列表。

纵向按 grow 权重分配，横向按 ratios；间隙与预设内边距用画布 pt 换算为归一化。
不读取字体度量。
"""

from __future__ import annotations

from pydantic import BaseModel

from app.domain.flex_layout import PRESET_INSET_PT, FlexContainer, FlexLeaf, FlexNode, GroupPreset
from app.domain.geometry import CANVAS_HEIGHT_PT, CANVAS_WIDTH_PT, Rect
from app.domain.slide_geometry import PlacedBlock


class SkinFrame(BaseModel):
    """容器子区域外框（preset inset 之前），供皮肤装饰使用。"""

    container_id: str
    preset: GroupPreset
    child_index: int
    rect: Rect


def solve(root: FlexContainer, canvas: Rect | None = None) -> list[PlacedBlock]:
    placed, _ = solve_with_frames(root, canvas)
    return placed


def solve_with_frames(
    root: FlexContainer, canvas: Rect | None = None
) -> tuple[list[PlacedBlock], list[SkinFrame]]:
    area = canvas or Rect(x=0.0, y=0.0, w=1.0, h=1.0)
    frames: list[SkinFrame] = []
    placed = _solve_container(root, area, frames)
    return placed, frames


def _solve_container(
    node: FlexContainer, area: Rect, frames: list[SkinFrame]
) -> list[PlacedBlock]:
    children = node.children
    if not children:
        return []

    child_areas = _split_area(node, area)
    placed: list[PlacedBlock] = []
    for index, (child, child_area) in enumerate(zip(children, child_areas, strict=True)):
        if node.preset is not None:
            frames.append(
                SkinFrame(
                    container_id=node.id,
                    preset=node.preset,
                    child_index=index,
                    rect=child_area,
                )
            )
        content = _apply_preset_inset(node, child_area)
        placed.extend(_solve_node(child, content, frames))
    return placed


def _solve_node(
    node: FlexNode, area: Rect, frames: list[SkinFrame]
) -> list[PlacedBlock]:
    if isinstance(node, FlexLeaf):
        return [
            PlacedBlock(
                block_id=node.block_id,
                rect=area,
                text_style=node.text_style,
            )
        ]
    return _solve_container(node, area, frames)


def _split_area(node: FlexContainer, area: Rect) -> list[Rect]:
    n = len(node.children)
    if n == 0:
        return []

    if node.type == "row":
        gap_norm = (n - 1) * node.gap_pt / CANVAS_WIDTH_PT if n > 1 else 0.0
        weights = _row_weights(node.ratios, n)
        total_w = max(area.w - gap_norm, 0.0)
        cursor = area.x
        rects: list[Rect] = []
        for index, weight in enumerate(weights):
            w = total_w * weight
            rects.append(Rect(x=cursor, y=area.y, w=max(w, 1e-9), h=area.h))
            cursor += w
            if index < n - 1:
                cursor += gap_norm
        return rects

    gap_norm = (n - 1) * node.gap_pt / CANVAS_HEIGHT_PT if n > 1 else 0.0
    weights = _column_weights(node.children)
    total_h = max(area.h - gap_norm, 0.0)
    cursor = area.y
    rects = []
    for index, weight in enumerate(weights):
        h = total_h * weight
        rects.append(Rect(x=area.x, y=cursor, w=area.w, h=max(h, 1e-9)))
        cursor += h
        if index < n - 1:
            cursor += gap_norm
    return rects


def _row_weights(ratios: list[float] | None, n: int) -> list[float]:
    if ratios is None or len(ratios) != n:
        return [1.0 / n] * n
    total = sum(ratios)
    if total <= 0:
        return [1.0 / n] * n
    return [r / total for r in ratios]


def _column_weights(children: list[FlexNode]) -> list[float]:
    grows = [child.grow for child in children]
    total = sum(grows)
    if total <= 0:
        n = len(children)
        return [1.0 / n] * n
    return [g / total for g in grows]


def _apply_preset_inset(container: FlexContainer, child_area: Rect) -> Rect:
    if container.preset is None:
        return child_area
    inset_pt = PRESET_INSET_PT[container.preset]
    inset_x = inset_pt / CANVAS_WIDTH_PT
    inset_y = inset_pt / CANVAS_HEIGHT_PT
    w = child_area.w - 2 * inset_x
    h = child_area.h - 2 * inset_y
    if w <= 0 or h <= 0:
        return child_area
    return Rect(
        x=child_area.x + inset_x,
        y=child_area.y + inset_y,
        w=w,
        h=h,
    )
