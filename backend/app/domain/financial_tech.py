"""Geometry for financial panels, shared with the browser renderer."""

from __future__ import annotations

import json
import math
from functools import lru_cache

from app.core.paths import SHARED_DIR
from app.domain.content import DiagramEdge, DiagramNode
from app.domain.geometry import CANVAS_HEIGHT_PT, CANVAS_WIDTH_PT, Rect


@lru_cache
def financial_tech_style() -> dict:
    return json.loads((SHARED_DIR / "financial-tech-style.json").read_text(encoding="utf-8"))


def panel_grid(count: int, width_pt: float, height_pt: float) -> tuple[int, float, float]:
    spec = financial_tech_style()
    gap = spec["card_gap_pt"]
    columns = min(
        count,
        spec["card_max_columns"],
        max(1, int((width_pt + gap) // (spec["card_min_width_pt"] + gap))),
    )
    rows = math.ceil(count / columns)
    return (
        columns,
        max(1.0, (width_pt - gap * (columns - 1)) / columns),
        max(1.0, (height_pt - gap * (rows - 1)) / rows),
    )


def panel_header_height(height_pt: float, size_pt: float, line_height: float) -> float:
    spec = financial_tech_style()
    return min(height_pt * 0.45, max(spec["header_min_height_pt"], size_pt * line_height * 2 + 12))


def platform_node_rects(
    nodes: list[DiagramNode],
    edges: list[DiagramEdge],
    rect: Rect,
) -> tuple[dict[str, Rect], str | None]:
    """Only a true star graph uses the hub view; other edges retain their topology."""
    width, height = rect.w * CANVAS_WIDTH_PT, rect.h * CANVAS_HEIGHT_PT
    gap = financial_tech_style()["node_gap_pt"]
    ids = {node.id for node in nodes}
    links = {node.id: set() for node in nodes}
    valid = [e for e in edges if e.source in ids and e.target in ids and e.source != e.target]
    for edge in valid:
        links[edge.source].add(edge.target)
        links[edge.target].add(edge.source)
    hub = next(
        (
            n.id
            for n in nodes
            if len(nodes) >= 4
            and links[n.id] == ids - {n.id}
            and all(e.source == n.id or e.target == n.id for e in valid)
        ),
        None,
    )
    boxes: dict[str, tuple[float, float, float, float]] = {}
    if hub and len(nodes) <= 7 and width >= 380 and height >= 240:
        side = [n for n in nodes if n.id != hub]
        rows = math.ceil(len(side) / 2)
        node_w = width * 0.26
        node_h = min(88.0, (height - gap * (rows - 1)) / rows)
        boxes[hub] = (width * 0.355, (height - node_h * 1.25) / 2, width * 0.29, node_h * 1.25)
        for index, node in enumerate(side):
            row = index // 2
            y = (height - (rows * node_h + (rows - 1) * gap)) / 2 + row * (node_h + gap)
            boxes[node.id] = (0 if index % 2 == 0 else width - node_w, y, node_w, node_h)
    else:
        hub = None
        incoming = dict.fromkeys(ids, 0)
        outgoing: dict[str, list[str]] = {node.id: [] for node in nodes}
        for edge in valid:
            outgoing[edge.source].append(edge.target)
            incoming[edge.target] += 1
        levels = {n.id: 0 for n in nodes if incoming[n.id] == 0}
        queue = list(levels)
        for current in queue:
            for target in outgoing[current]:
                levels[target] = max(levels.get(target, 0), levels[current] + 1)
                incoming[target] -= 1
                if incoming[target] == 0:
                    queue.append(target)
        # Cycles and disconnected cyclic components use a grid without inventing edges.
        if len(queue) != len(nodes):
            levels = {n.id: index // 3 for index, n in enumerate(nodes)}
        groups: dict[int, list[DiagramNode]] = {}
        for node in nodes:
            groups.setdefault(levels[node.id], []).append(node)
        rows = [
            (level, group[start : start + 4])
            for level, group in sorted(groups.items())
            for start in range(0, len(group), 4)
        ]
        row_gap = min(gap, height / (len(rows) * 2))
        row_h = max(0.001, (height - row_gap * (len(rows) - 1)) / len(rows))
        for row_index, (_, group) in enumerate(rows):
            column_gap = min(gap, width / (len(group) * 2))
            node_w = max(0.001, (width - column_gap * (len(group) - 1)) / len(group))
            for column, node in enumerate(group):
                boxes[node.id] = (
                    column * (node_w + column_gap),
                    row_index * (row_h + row_gap),
                    node_w,
                    row_h,
                )
    return (
        {
            key: Rect(
                x=rect.x + x / CANVAS_WIDTH_PT,
                y=rect.y + y / CANVAS_HEIGHT_PT,
                w=w / CANVAS_WIDTH_PT,
                h=h / CANVAS_HEIGHT_PT,
            )
            for key, (x, y, w, h) in boxes.items()
        },
        hub,
    )
