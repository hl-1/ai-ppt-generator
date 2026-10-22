"""Content-driven, lossless table sizing used by preview, validation and export."""

from __future__ import annotations

import math

from app.engine.content.content import FinancialTableBlock, TableBlock, TableGeometry
from app.engine.layout.text_metrics import wrap_text


def table_cells(block: TableBlock | FinancialTableBlock) -> list[list[str]]:
    if isinstance(block, FinancialTableBlock):
        return [
            [block.unit or "", *block.columns],
            *[[row.label, *row.values] for row in block.rows],
        ]
    return [block.header, *block.rows]


def layout_table(
    block: TableBlock | FinancialTableBlock,
    width: float,
    height: float,
    *,
    max_font: float = 16,
    min_font: float = 12,
) -> TableGeometry:
    cells = table_cells(block)
    count = max(map(len, cells), default=1)
    cells = [row + [""] * (count - len(row)) for row in cells]
    pad = 7.0
    weights = [math.sqrt(max(4, sum(len(row[c]) for row in cells))) for c in range(count)]
    minimum = min(76.0, width / count * 0.7)
    remaining = max(0, width - minimum * count)
    widths = [minimum + remaining * weight / sum(weights) for weight in weights]

    def measure(columns: list[float], font: float):
        wrapped = [
            [
                "\n".join(wrap_text(value, width_pt=max(1, columns[c] - 2 * pad - 2), size_pt=font))
                for c, value in enumerate(row)
            ]
            for row in cells
        ]
        heights = [
            max(text.count("\n") + 1 for text in row) * font * 1.25 + 2 * pad for row in wrapped
        ]
        return wrapped, heights

    font = max(min_font, max_font)
    while True:
        wrapped, heights = measure(widths, font)
        # Move width to the column that reduces actual wrapped height the most.
        for _ in range(16):
            best = sum(heights)
            chosen = None
            for donor in range(count):
                if widths[donor] - 12 < minimum:
                    continue
                for receiver in range(count):
                    if receiver == donor:
                        continue
                    candidate = list(widths)
                    candidate[donor] -= 12
                    candidate[receiver] += 12
                    lines, row_heights = measure(candidate, font)
                    if sum(row_heights) < best - 0.1:
                        chosen = candidate, lines, row_heights
                        best = sum(row_heights)
            if chosen is None:
                break
            widths, wrapped, heights = chosen
        if sum(heights) <= height + 0.1 or font <= min_font:
            return TableGeometry(
                column_widths=widths,
                row_heights=heights,
                cells=wrapped,
                font_size=font,
                width=width,
                height=sum(heights),
                padding=pad,
            )
        font = max(min_font, font - 1)


def table_row_groups(geometry: TableGeometry, height: float) -> list[list[int]]:
    """Repeat the header; never drop a row or silently shrink below readable size."""
    groups: list[list[int]] = [[]]
    used = geometry.row_heights[0]
    for index, row_height in enumerate(geometry.row_heights[1:]):
        if row_height + geometry.row_heights[0] > height + 0.5:
            raise ValueError("A table row exceeds one slide; split the row content before export")
        if groups[-1] and used + row_height > height + 0.5:
            groups.append([])
            used = geometry.row_heights[0]
        groups[-1].append(index)
        used += row_height
    return groups
