"""Generate geometry fixtures for the TypeScript parity check."""

import json

from app.core.paths import SHARED_DIR
from app.domain.content import DiagramBlock, DiagramEdge, DiagramNode
from app.domain.financial_tech import panel_grid, platform_node_rects
from app.domain.geometry import CANVAS_HEIGHT_PT, CANVAS_WIDTH_PT, Rect
from app.domain.sample import load_financial_tech_sample


def main() -> None:
    cases = []
    diagrams = [
        block
        for slide in load_financial_tech_sample().slides
        for block in slide.blocks
        if isinstance(block, DiagramBlock)
    ]
    diagrams.extend(
        [
            DiagramBlock(
                id="partial-cycle",
                slot_id="visual",
                diagram_type="flow",
                nodes=[DiagramNode(id=str(index), title=str(index)) for index in range(3)],
                edges=[
                    DiagramEdge(source="0", target="1"),
                    DiagramEdge(source="0", target="2"),
                    DiagramEdge(source="1", target="2"),
                    DiagramEdge(source="2", target="1"),
                ],
            ),
            DiagramBlock(
                id="long-chain",
                slot_id="visual",
                diagram_type="flow",
                nodes=[DiagramNode(id=str(index), title=str(index)) for index in range(18)],
                edges=[
                    DiagramEdge(source=str(index), target=str(index + 1)) for index in range(17)
                ],
            ),
        ]
    )
    for block in diagrams:
        for width, height in [(856, 320), (300, 240), (650, 180)]:
            boxes, hub = platform_node_rects(
                block.nodes,
                block.edges,
                Rect(x=0, y=0, w=width / CANVAS_WIDTH_PT, h=height / CANVAS_HEIGHT_PT),
            )
            cases.append(
                {
                    "nodes": [node.model_dump() for node in block.nodes],
                    "edges": [edge.model_dump() for edge in block.edges],
                    "width": width,
                    "height": height,
                    "hub": hub,
                    "rects": {
                        key: {
                            "x": box.x * CANVAS_WIDTH_PT,
                            "y": box.y * CANVAS_HEIGHT_PT,
                            "w": box.w * CANVAS_WIDTH_PT,
                            "h": box.h * CANVAS_HEIGHT_PT,
                        }
                        for key, box in boxes.items()
                    },
                }
            )
    panels = [
        {"count": count, "width": width, "height": 320, "expected": panel_grid(count, width, 320)}
        for count, width in [(1, 120), (4, 856), (6, 520), (9, 350)]
    ]
    path = SHARED_DIR / "financial-tech-fixtures.json"
    path.write_text(
        json.dumps({"diagrams": cases, "panels": panels}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(path)


if __name__ == "__main__":
    main()
