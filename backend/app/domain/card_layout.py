"""Card geometry and text requirements shared by fitting, validation and export."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from functools import lru_cache

from app.core.paths import SHARED_DIR
from app.domain.block_style import merge_text_style, resolve_box
from app.domain.content import CardsBlock
from app.domain.geometry import CANVAS_HEIGHT_PT
from app.domain.text_metrics import measure_text
from app.domain.theme import Theme


@lru_cache
def card_style(visual_style: str = "standard") -> dict:
    spec = json.loads((SHARED_DIR / "card-layout.json").read_text(encoding="utf-8"))
    if visual_style == "financial-tech":
        financial = json.loads(
            (SHARED_DIR / "financial-tech-style.json").read_text(encoding="utf-8")
        )
        spec = {
            **spec,
            "gap_pt": financial["card_gap_pt"],
            "padding_pt": financial["card_padding_pt"],
            "min_width_pt": financial["card_min_width_pt"],
            "max_columns": financial["card_max_columns"],
            "header_min_height_pt": financial["header_min_height_pt"],
            **{key: value for key, value in financial.items() if key.startswith("header_")},
        }
    return spec


def card_grid(
    count: int, width_pt: float, height_pt: float, *, visual_style: str = "standard"
) -> tuple[int, float, float]:
    spec = card_style(visual_style)
    gap = spec["gap_pt"]
    columns = max(
        1,
        min(count, spec["max_columns"], int((width_pt + gap) // (spec["min_width_pt"] + gap))),
    )
    rows = max(1, math.ceil(count / columns))
    columns = max(1, math.ceil(count / rows))
    return (
        columns,
        max(1.0, (width_pt - gap * (columns - 1)) / columns),
        max(1.0, (height_pt - gap * (rows - 1)) / rows),
    )


def card_header_height(height_pt: float, size_pt: float, line_height: float) -> float:
    spec = card_style("financial-tech")
    return min(height_pt * 0.45, max(spec["header_min_height_pt"], size_pt * line_height * 2 + 12))


def card_header_inset(width_pt: float) -> float:
    spec = card_style("financial-tech")
    return max(
        spec["header_padding_pt"],
        width_pt * spec["header_notch_ratio"] + spec["header_safe_padding_pt"],
    )


@dataclass(frozen=True)
class CardMeasure:
    title_height: float
    desc_height: float
    required_height: float
    line_count: int
    used_estimate: bool


def measure_cards(
    block: CardsBlock, theme: Theme, width_pt: float
) -> tuple[int, list[CardMeasure]]:
    """Measure every card at its actual column width, including multi-row grids."""
    spec = card_style(theme.visual_style)
    box = resolve_box(theme, block.style)
    outer = box.padding_pt + box.border_width_pt
    columns, width, _ = card_grid(
        len(block.items),
        width_pt - 2 * outer,
        CANVAS_HEIGHT_PT,
        visual_style=theme.visual_style,
    )
    title_style = merge_text_style(theme, "subtitle", block.style)
    body_style = merge_text_style(theme, "body", block.style)
    pad = spec["padding_pt"]
    financial = theme.visual_style == "financial-tech"
    measures = []
    for item in block.items:
        title = f"{item.icon} {item.title}".strip() if item.icon and not financial else item.title
        title_result = measure_text(
            title,
            style=title_style,
            width_pt=max(
                1,
                width
                - (
                    2 * card_header_inset(width)
                    + spec["header_icon_width_pt"]
                    + spec["header_icon_gap_pt"]
                    if financial
                    else 2 * pad
                ),
            ),
            height_pt=CANVAS_HEIGHT_PT,
        )
        desc_result = measure_text(
            item.desc,
            style=body_style,
            width_pt=max(1, width - 2 * pad),
            height_pt=CANVAS_HEIGHT_PT,
        )
        title_h = title_result.height_pt * spec["breathing"]
        desc_h = desc_result.height_pt * spec["breathing"]
        if financial:
            header = max(
                card_header_height(CANVAS_HEIGHT_PT, title_style.size_pt, title_style.line_height),
                title_h + 12,
            )
            required = max(header + desc_h + 2 * pad + 18, header / 0.45)
        else:
            required = title_h + desc_h + spec["text_gap_pt"] + 2 * pad
        measures.append(
            CardMeasure(
                title_h,
                desc_h,
                required,
                title_result.line_count + desc_result.line_count,
                title_result.used_estimate or desc_result.used_estimate,
            )
        )
    return columns, measures


def cards_natural_height(block: CardsBlock, theme: Theme, width_pt: float) -> float:
    if not block.items:
        return 0.0
    spec = card_style(theme.visual_style)
    columns, measures = measure_cards(block, theme, width_pt)
    rows = math.ceil(len(block.items) / columns)
    box = resolve_box(theme, block.style)
    return (
        rows * max(item.required_height for item in measures)
        + (rows - 1) * spec["gap_pt"]
        + 2 * (box.padding_pt + box.border_width_pt)
    )
