from __future__ import annotations

from app.engine.content.content import FinancialTableBlock, Slide, TableBlock
from app.engine.layout.slide_geometry import placed_by_block_id
from app.engine.layout.table_layout import table_row_groups


def split_table_slide(slide: Slide) -> list[Slide]:
    tables = [b for b in slide.blocks if isinstance(b, (TableBlock, FinancialTableBlock))]
    placed = placed_by_block_id(slide)
    overflowing = [
        b
        for b in tables
        if b.geometry
        and b.id in placed
        and b.geometry.height > placed[b.id].rect.to_points()[3] + 0.5
    ]
    if not overflowing:
        return [slide]
    if len(tables) != 1:
        raise ValueError("Multiple overflowing tables need separate slide areas")
    table = overflowing[0]
    if table.locked:
        raise ValueError("The overflowing table is locked")
    g = table.geometry
    groups = table_row_groups(g, placed[table.id].rect.to_points()[3])
    result = []
    for group in groups:
        rows = [table.rows[i] for i in group]
        geometry = g.model_copy(
            update={
                "row_heights": [g.row_heights[0], *[g.row_heights[i + 1] for i in group]],
                "cells": [g.cells[0], *[g.cells[i + 1] for i in group]],
                "height": g.row_heights[0] + sum(g.row_heights[i + 1] for i in group),
            }
        )
        chunk = table.model_copy(update={"rows": rows, "geometry": geometry})
        result.append(
            slide.model_copy(
                update={"blocks": [chunk if b.id == table.id else b for b in slide.blocks]}
            )
        )
    return result
