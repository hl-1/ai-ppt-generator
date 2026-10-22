"""Derive visual geometry only after page geometry has been finalized."""

from __future__ import annotations

from app.engine.content.content import DiagramBlock, FinancialTableBlock, Slide, TableBlock
from app.engine.content.source import SourceSection
from app.engine.diagram.diagram_layout import layout_diagram, parse_mermaid
from app.engine.diagram.flow_policy import is_numbered_steps
from app.engine.layout.slide_geometry import placed_by_block_id
from app.engine.layout.table_layout import layout_table
from app.engine.layout.theme import Theme


def bind_source_diagram(slide: Slide, sections: list[SourceSection], *, requested: bool) -> Slide:
    diagrams = [diagram for section in sections for diagram in section.diagrams]
    existing = next((b for b in slide.blocks if isinstance(b, DiagramBlock)), None)
    if not requested and existing is None:
        return slide
    if existing and existing.locked:
        return slide
    # Only authored source can replace a graph; generated Mermaid is a derived view.
    if existing and existing.diagram_type == "timeline":
        return slide
    source = diagrams[0].source if len(diagrams) == 1 else None
    if not source:
        return slide
    if existing is None and requested:
        existing = next((b for b in slide.blocks if is_numbered_steps(b)), None)
        if existing and existing.locked:
            return slide
    nodes, edges, direction = parse_mermaid(source)
    block = DiagramBlock(
        id=existing.id if existing else f"{slide.id}-source-diagram",
        slot_id=existing.slot_id if existing else "visual",
        diagram_type="flow",
        nodes=nodes,
        edges=edges,
        direction=direction,
        mermaid=source,
        style=existing.style if existing else None,
    )
    return slide.model_copy(
        update={"blocks": [b for b in slide.blocks if b is not existing] + [block]}
    )


def prepare_visual_layout(slide: Slide, theme: Theme) -> Slide:
    placed = placed_by_block_id(slide)
    blocks = []
    for block in slide.blocks:
        placement = placed.get(block.id)
        if placement:
            _, _, width, height = placement.rect.to_points()
            if isinstance(block, DiagramBlock) and block.diagram_type != "timeline":
                block = block.model_copy(update={"geometry": layout_diagram(block, width, height)})
            elif isinstance(block, (TableBlock, FinancialTableBlock)):
                font = block.style.size_pt if block.style and block.style.size_pt else 16
                block = block.model_copy(
                    update={
                        "geometry": layout_table(block, width, height, max_font=font),
                    }
                )
        blocks.append(block)
    return slide.model_copy(update={"blocks": blocks})
