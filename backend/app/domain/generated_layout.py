"""Choose readable generated layouts using the final theme and complete content.

Only generation calls this module. Manual layouts and locked blocks retain their tree.
"""

from __future__ import annotations

from app.domain.content import CardsBlock, Slide, TextBlock
from app.domain.content_format import has_temporal_sequence
from app.domain.flex_layout import FlexContainer, FlexLeaf
from app.domain.slide_geometry import placed_by_block_id
from app.domain.theme import Theme
from app.domain.theme_layout import reflow_slide_to_theme
from app.domain.validation import _measure_block_overflow, validate_slide


def normalize_generated_diagrams(slide: Slide, *, visual_type: str = "auto") -> Slide:
    if visual_type != "auto":
        return slide
    blocks = []
    for block in slide.blocks:
        if (
            block.type == "diagram"
            and block.diagram_type == "timeline"
            and not block.locked
            and not has_temporal_sequence([node.title for node in block.nodes])
        ):
            block = CardsBlock(
                **block.model_dump(include={"id", "slot_id", "locked", "style"}),
                items=[{"title": node.title, "desc": node.desc} for node in block.nodes],
            )
        blocks.append(block)
    return slide.model_copy(update={"blocks": blocks})


def title_block(slide: Slide):
    placed = placed_by_block_id(slide)
    return next(
        (
            block
            for block in slide.blocks
            if block.type == "text"
            and (
                block.slot_id in {"title", "heading", "display"}
                or block.id == "title"
                or block.id.endswith("-title")
                or (block.id in placed and placed[block.id].text_style in {"title", "display"})
            )
        ),
        None,
    )


def safe_layout(slide: Slide, *, paired: bool = False) -> Slide:
    """Group introductory text above content; never make a label a body column."""
    title = title_block(slide)
    placed = placed_by_block_id(slide)

    def leaf(block):
        style = placed[block.id].text_style if block.id in placed else None
        if block is title:
            style = "title"
        elif block.slot_id == "agenda_heading":
            style = "subtitle"
        elif isinstance(block, TextBlock) and len(block.text) <= 16:
            style = "caption"
        return FlexLeaf(id=f"leaf-{block.id}", block_id=block.id, text_style=style)

    body = [block for block in slide.blocks if block is not title]
    prefix = []
    while body and isinstance(body[0], TextBlock) and len(body[0].text) <= 100:
        prefix.append(body.pop(0))
    nodes = [leaf(block) for block in ([title] if title else []) + prefix]
    if paired and 2 <= len(body) <= 3:
        nodes.append(
            FlexContainer(
                type="row",
                id="content-groups",
                gap_pt=24,
                children=[leaf(block) for block in body],
            )
        )
    else:
        nodes.extend(leaf(block) for block in body)
    return slide.model_copy(
        update={
            "layout_mode": "flex",
            "layout_tree": FlexContainer(
                type="column",
                id="content-report",
                gap_pt=14,
                children=nodes,
            ),
        }
    )


def _score(slide: Slide, theme: Theme) -> float:
    issues = validate_slide(slide, theme=theme)
    score = 1000 * sum(issue.severity == "error" and issue.code != "overflow" for issue in issues)
    placed = placed_by_block_id(slide)
    block_map = {block.id: block for block in slide.blocks}

    def labels(node):
        if isinstance(node, FlexLeaf):
            block = block_map.get(node.block_id)
            return (
                isinstance(block, TextBlock)
                and len(block.text) <= 16
                and block.slot_id != "agenda_heading"
            )
        children = [
            child for child in node.children if isinstance(child, FlexLeaf) or child.children
        ]
        return bool(children) and all(labels(child) for child in children)

    def grouping_penalty(node):
        if isinstance(node, FlexLeaf):
            return 0
        return (
            5
            if node.type == "row"
            and any(labels(child) for child in node.children)
            and not all(labels(child) for child in node.children)
            else 0
        ) + sum(grouping_penalty(child) for child in node.children)

    score += grouping_penalty(slide.layout_tree) if slide.layout_tree else 0
    for block in slide.blocks:
        if block.id not in placed:
            continue
        area = placed[block.id]
        for _, needed, available, _, _ in _measure_block_overflow(
            block,
            rect=area.rect,
            text_style=area.text_style,
            theme=theme,
        ):
            score += max(0.0, needed - available - 0.5) / max(1.0, available)
    return score


def fit_generated_slide(slide: Slide, theme: Theme, *, page_role: str | None = None) -> Slide:
    fitted = reflow_slide_to_theme(slide, theme, page_role=page_role)
    if slide.layout_mode != "flex" or any(block.locked for block in slide.blocks):
        return fitted
    score = _score(fitted, theme)
    if score == 0:
        return fitted
    # The preassigned template is a preference. Capacity takes precedence.
    for paired in (True, False):
        candidate = reflow_slide_to_theme(
            safe_layout(slide, paired=paired), theme, page_role=page_role
        )
        candidate_score = _score(candidate, theme)
        if candidate_score < score:
            fitted, score = candidate, candidate_score
        if score == 0:
            break
    return fitted
