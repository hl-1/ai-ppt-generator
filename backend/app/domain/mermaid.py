from __future__ import annotations

import re
from collections.abc import Sequence
from html import escape

from app.domain.content import DiagramEdge, DiagramKind, DiagramNode
from app.domain.flow_policy import should_keep_flow_diagram


def normalize_flow_edges(
    diagram_type: DiagramKind,
    nodes: Sequence[DiagramNode],
    edges: Sequence[DiagramEdge],
) -> list[DiagramEdge]:
    """把有复杂语义但仍为线性拓扑的流程补成分流/汇聚结构。"""
    original = list(edges)
    if diagram_type != "flow" or len(nodes) < 4:
        return original

    node_ids = {node.id for node in nodes}
    valid = [
        edge
        for edge in original
        if edge.source in node_ids and edge.target in node_ids and edge.source != edge.target
    ]
    if _has_branch_or_merge(valid):
        return valid
    if not should_keep_flow_diagram(nodes, valid):
        return valid
    return _branch_merge_edges(nodes)


def _has_branch_or_merge(edges: Sequence[DiagramEdge]) -> bool:
    outgoing: dict[str, int] = {}
    incoming: dict[str, int] = {}
    for edge in edges:
        outgoing[edge.source] = outgoing.get(edge.source, 0) + 1
        incoming[edge.target] = incoming.get(edge.target, 0) + 1
    return any(count > 1 for count in outgoing.values()) or any(
        count > 1 for count in incoming.values()
    )


def _branch_merge_edges(nodes: Sequence[DiagramNode]) -> list[DiagramEdge]:
    """按起点、分流、并行处理、汇聚生成稳定的 TB 拓扑。"""
    if len(nodes) < 4:
        return [
            DiagramEdge(source=left.id, target=right.id)
            for left, right in zip(nodes, nodes[1:], strict=False)
        ]

    branch_index = 1 if len(nodes) >= 6 else 0
    merge_index = len(nodes) - 3 if len(nodes) >= 6 else len(nodes) - 1
    if merge_index <= branch_index + 1:
        return [
            DiagramEdge(source=left.id, target=right.id)
            for left, right in zip(nodes, nodes[1:], strict=False)
        ]

    result: list[DiagramEdge] = []
    if branch_index > 0:
        result.append(DiagramEdge(source=nodes[0].id, target=nodes[branch_index].id))
    for node in nodes[branch_index + 1 : merge_index]:
        result.append(DiagramEdge(source=nodes[branch_index].id, target=node.id))
        result.append(DiagramEdge(source=node.id, target=nodes[merge_index].id))
    result.extend(
        DiagramEdge(source=left.id, target=right.id)
        for left, right in zip(nodes[merge_index:], nodes[merge_index + 1 :], strict=False)
    )
    return result


def mermaid_for_diagram(
    diagram_type: DiagramKind,
    nodes: Sequence[DiagramNode],
    edges: Sequence[DiagramEdge],
    *,
    direction: str | None = None,
) -> str:
    """Build a safe Mermaid flowchart from the editable diagram model."""
    normalized_edges = (
        [] if diagram_type == "timeline" else normalize_flow_edges(diagram_type, nodes, edges)
    )
    flow_direction = direction or "TB"
    lines = [f"flowchart {flow_direction}"]
    node_ids: dict[str, str] = {}

    for index, node in enumerate(nodes, start=1):
        node_id = _safe_node_id(node.id, index)
        node_ids[node.id] = node_id
        lines.append(f'    {node_id}["{_label(node.title, node.desc)}"]')

    for edge in normalized_edges:
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
    """Keep authored Mermaid except for timelines, whose stages remain unconnected."""
    if diagram_type == "timeline":
        return mermaid_for_diagram(diagram_type, nodes, edges, direction=direction)
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
