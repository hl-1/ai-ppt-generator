"""Parse source graphs and share ELK geometry across web and editable PPTX."""

from __future__ import annotations

import json
import shutil
import subprocess
from functools import lru_cache

from app.core.paths import DIAGRAM_ENGINE
from app.engine.content.content import (
    DiagramBlock,
    DiagramEdge,
    DiagramEdgeGeometry,
    DiagramGeometry,
    DiagramNode,
    DiagramNodeGeometry,
)
from app.engine.diagram.diagram_style import FLOWCHART_STYLE
from app.engine.layout.text_metrics import wrap_text

ENGINE = DIAGRAM_ENGINE


@lru_cache(maxsize=256)
def _run(payload: str):
    node = shutil.which("node")
    if not node:
        raise RuntimeError(
            "Diagram layout requires Node.js; install tools/diagram-engine dependencies"
        )
    result = subprocess.run(
        [node, str(ENGINE)],
        input=payload,
        capture_output=True,
        encoding="utf-8",
        timeout=45,
        check=False,
    )
    if result.returncode:
        raise ValueError(f"Diagram engine: {result.stderr[:500]}")
    return json.loads(result.stdout)


def parse_mermaid(source: str) -> tuple[list[DiagramNode], list[DiagramEdge], str]:
    parsed = _run(json.dumps({"action": "parse", "source": source}))
    direction = parsed["direction"].replace("TD", "TB")
    return (
        [DiagramNode.model_validate(n) for n in parsed["nodes"]],
        [DiagramEdge.model_validate(e) for e in parsed["edges"]],
        direction if direction in {"TB", "LR", "BT", "RL"} else "TB",
    )


def _valid_routes(graph: dict, block: DiagramBlock) -> bool:
    nodes = {node["id"]: node for node in graph["children"]}
    if set(nodes) != {node.id for node in block.nodes} or len(graph["edges"]) != len(block.edges):
        return False

    def attached(point: dict, node: dict) -> bool:
        x, y, w, h = (node[key] for key in ("x", "y", "width", "height"))
        px, py = point["x"], point["y"]
        return (
            x - 0.01 <= px <= x + w + 0.01
            and y - 0.01 <= py <= y + h + 0.01
            and min(abs(px - x), abs(px - x - w), abs(py - y), abs(py - y - h)) < 0.01
        )

    for edge, expected in zip(graph["edges"], block.edges, strict=True):
        if edge["sources"] != [expected.source] or edge["targets"] != [expected.target]:
            return False
        sections = edge.get("sections", [])
        if len(sections) != 1:
            return False
        section = sections[0]
        if not attached(section["startPoint"], nodes[expected.source]) or not attached(
            section["endPoint"], nodes[expected.target]
        ):
            return False
        points = [section["startPoint"], *section.get("bendPoints", []), section["endPoint"]]
        if any(
            abs(a["x"] - b["x"]) > 0.01 and abs(a["y"] - b["y"]) > 0.01
            for a, b in zip(points, points[1:], strict=False)
        ):
            return False
    return True


def layout_diagram(block: DiagramBlock, width: float, height: float) -> DiagramGeometry:
    style = FLOWCHART_STYLE
    font = (
        max(10, block.style.size_pt) if block.style and block.style.size_pt else style["font_size"]
    )
    label_font = font * style["label_font_ratio"]
    candidates = []
    text_candidates = []
    for node_width in style["node_widths"]:
        texts = {}
        children = []
        for node in block.nodes:
            inner = node_width - 2 * style["node_padding"]
            title = wrap_text(node.title, width_pt=inner, size_pt=font)
            desc = wrap_text(node.desc, width_pt=inner, size_pt=font) if node.desc else []
            node_height = max(40, (len(title) + len(desc)) * font * 1.25 + 18)
            texts[node.id] = (title, desc)
            children.append({"id": node.id, "width": node_width, "height": node_height})
        edges = []
        for edge in block.edges:
            lines = wrap_text(edge.label or "", width_pt=112, size_pt=label_font)
            edges.append(
                {
                    **edge.model_dump(),
                    "label": "\n".join(lines) if edge.label else None,
                    "label_width": min(112, max(map(len, lines), default=0) * label_font)
                    + 2 * style["label_padding_x"],
                    "label_height": len(lines) * label_font * style["line_height"]
                    + 2 * style["label_padding_y"],
                }
            )
        preferred = {"TB": "DOWN", "LR": "RIGHT", "BT": "UP", "RL": "LEFT"}[block.direction]
        for direction, wrap in ((preferred, False), ("DOWN", True), ("RIGHT", True)):
            candidates.append(
                {
                    "nodes": children,
                    "edges": edges,
                    "direction": direction,
                    "wrap": wrap,
                    "aspectRatio": width / max(height, 1),
                }
            )
            text_candidates.append(texts)
    graphs = _run(json.dumps({"action": "layout", "graphs": candidates}))
    valid = [i for i, graph in enumerate(graphs) if _valid_routes(graph, block)]
    if not valid:
        raise ValueError("Diagram layout failed to connect all source and target nodes")

    def score(i):
        graph = graphs[i]
        scale = min(width / max(graph["width"], 1), height / max(graph["height"], 1), 1.0)
        # Equal-size layouts favor wider, less fragmented text and useful page coverage.
        return (
            round(scale, 3),
            -sum(len(t) + len(d) for t, d in text_candidates[i].values()),
            min(graph["width"] / width, 1) * min(graph["height"] / height, 1),
        )

    index = max(
        valid,
        key=score,
    )
    graph = graphs[index]
    scale = min(width / max(graph["width"], 1), height / max(graph["height"], 1), 1.0)
    dx = (width - graph["width"] * scale) / 2
    dy = (height - graph["height"] * scale) / 2
    nodes = [
        DiagramNodeGeometry(
            id=n["id"],
            x=dx + n["x"] * scale,
            y=dy + n["y"] * scale,
            width=n["width"] * scale,
            height=n["height"] * scale,
            title_lines=text_candidates[index][n["id"]][0],
            desc_lines=text_candidates[index][n["id"]][1],
        )
        for n in graph["children"]
    ]
    edges = []
    for edge in graph["edges"]:
        label = next(iter(edge.get("labels", [])), {})
        for section in edge.get("sections", []):
            points = [section["startPoint"], *section.get("bendPoints", []), section["endPoint"]]
            edges.append(
                DiagramEdgeGeometry(
                    points=[(dx + p["x"] * scale, dy + p["y"] * scale) for p in points],
                    label=label.get("text"),
                    label_x=dx + label.get("x", 0) * scale,
                    label_y=dy + label.get("y", 0) * scale,
                    label_width=label.get("width", 0) * scale,
                    label_height=label.get("height", 0) * scale,
                )
            )
    return DiagramGeometry(
        version=style["version"],
        width=width,
        height=height,
        font_size=font * scale,
        nodes=nodes,
        edges=edges,
    )


def resolve_diagram_geometry(block: DiagramBlock, width: float, height: float) -> DiagramGeometry:
    geometry = block.geometry
    if (
        geometry is None
        or geometry.version != FLOWCHART_STYLE["version"]
        or abs(geometry.width - width) > 0.5
        or abs(geometry.height - height) > 0.5
    ):
        return layout_diagram(block, width, height)
    return geometry
