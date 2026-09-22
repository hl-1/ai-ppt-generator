from __future__ import annotations

import re
from collections.abc import Sequence
from html import escape

from app.domain.content import DiagramEdge, DiagramKind, DiagramNode


def mermaid_for_diagram(
    diagram_type: DiagramKind,
    nodes: Sequence[DiagramNode],
    edges: Sequence[DiagramEdge],
    *,
    direction: str | None = None,
) -> str:
    """Build a safe Mermaid flowchart from the editable diagram model."""
    flow_direction = direction or "TB"
    lines = [f"flowchart {flow_direction}"]
    node_ids: dict[str, str] = {}

    for index, node in enumerate(nodes, start=1):
        node_id = _safe_node_id(node.id, index)
        node_ids[node.id] = node_id
        lines.append(f'    {node_id}["{_label(node.title, node.desc)}"]')

    for edge in edges:
        source = node_ids.get(edge.source)
        target = node_ids.get(edge.target)
        if source is None or target is None:
            continue
        label = _clean_label(edge.label)
        if label:
            lines.append(f"    {source} -->|{label}| {target}")
        else:
            lines.append(f"    {source} --> {target}")

    return "\n".join(lines)


def ensure_mermaid(
    mermaid: str | None,
    diagram_type: DiagramKind,
    nodes: Sequence[DiagramNode],
    edges: Sequence[DiagramEdge],
    *,
    direction: str | None = None,
) -> str:
    """Keep authored Mermaid when present and generate it for legacy blocks."""
    if mermaid and mermaid.strip():
        return mermaid.strip()
    return mermaid_for_diagram(diagram_type, nodes, edges, direction=direction)


def _safe_node_id(raw: str, index: int) -> str:
    value = re.sub(r"[^A-Za-z0-9_]", "_", raw).strip("_")
    return f"node_{value or index}_{index}"


def _label(title: str, desc: str) -> str:
    parts = [_clean_label(title)]
    if desc.strip():
        parts.append(_clean_label(desc))
    return "<br/>".join(part for part in parts if part)


def _clean_label(value: str | None) -> str:
    if not value:
        return ""
    text = " ".join(value.replace("|", "/").split())
    return escape(text, quote=True)
