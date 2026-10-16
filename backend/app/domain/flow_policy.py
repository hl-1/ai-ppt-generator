from __future__ import annotations

import re
from collections.abc import Sequence

from app.domain.content import BulletsBlock, CardItem, DiagramBlock, DiagramEdge, DiagramNode, Slide

_STEP_PREFIXES = (
    "第一步",
    "第二步",
    "第三步",
    "第四步",
    "第五步",
    "第六步",
    "第七步",
    "第八步",
    "第九步",
    "前两步",
    "最后一步",
    "步骤一",
    "步骤二",
    "步骤三",
    "步骤四",
    "步骤五",
)


def has_branching_edges(edges: Sequence[DiagramEdge]) -> bool:
    outgoing: dict[str, set[str]] = {}
    incoming: dict[str, set[str]] = {}
    for edge in edges:
        outgoing.setdefault(edge.source, set()).add(edge.target)
        incoming.setdefault(edge.target, set()).add(edge.source)
    return any(len(targets) > 1 for targets in outgoing.values()) or any(
        len(sources) > 1 for sources in incoming.values()
    )


def should_keep_flow_diagram(
    nodes: Sequence[DiagramNode],
    edges: Sequence[DiagramEdge],
    *,
    context: Sequence[str] = (),
) -> bool:
    """Require connected nonlinear topology and, when supplied, original text evidence."""
    ids = {node.id for node in nodes}
    if len(ids) < 3 or len(ids) != len(nodes) or not edges:
        return False
    if any(edge.source not in ids or edge.target not in ids for edge in edges):
        return False
    neighbors: dict[str, set[str]] = {node_id: set() for node_id in ids}
    outgoing: dict[str, set[str]] = {node_id: set() for node_id in ids}
    for edge in edges:
        neighbors[edge.source].add(edge.target)
        neighbors[edge.target].add(edge.source)
        outgoing[edge.source].add(edge.target)
    visited: set[str] = set()
    pending = [nodes[0].id]
    while pending:
        current = pending.pop()
        if current not in visited:
            visited.add(current)
            pending.extend(neighbors[current] - visited)
    if visited != ids:
        return False

    # Kahn's algorithm also detects pure cycles with no branch/merge node.
    indegree = {node_id: 0 for node_id in ids}
    for targets in outgoing.values():
        for target in targets:
            indegree[target] += 1
    pending = [node_id for node_id, degree in indegree.items() if degree == 0]
    removed = 0
    while pending:
        current = pending.pop()
        removed += 1
        for target in outgoing[current]:
            indegree[target] -= 1
            if indegree[target] == 0:
                pending.append(target)
    cyclic = removed != len(ids)
    branching = has_branching_edges(edges)
    if not branching and not cyclic:
        return False
    if not context:
        return True
    # Generated labels cannot serve as evidence for their own invented relationships.
    blob = "\n".join(context).lower()
    conditional = bool(
        re.search(
            r"(?:如果|假如|若|是否|有无|能否|条件|if\b|when\b)[\s\S]{0,160}"
            r"(?:否则|不通过|未通过|失败|驳回|则|那么|分别|else\b|then\b)",
            blob,
        )
        or re.search(r"(?:通过|成功)[\s\S]{0,100}(?:不通过|未通过|失败|驳回)", blob)
    )
    parallel = bool(
        re.search(
            r"(?:并行|并发)(?:地)?(?:执行|处理|校验|检索|查询|调用|运行)"
            r"|(?:并行|并发)[^\n。；]{0,80}(?:汇总|合并|汇合|汇聚)"
            r"|同时[\s\S]{0,60}(?:调用|执行|处理|校验|检索|查询)"
            r"|\b(?:parallel|concurrent)(?:ly)?\b[\s\S]{0,100}\b(?:run|execute|process|merge|join)\b",
            blob,
        )
    )
    loop = bool(
        re.search(
            r"(?:失败|超时|未通过|不满足)[\s\S]{0,100}(?:重试|返回|回到|重新|再次)"
            r"|(?:循环|重复)[\s\S]{0,100}(?:直到|直至|满足|条件)"
            r"|\b(?:fail\w*|timeout|until)\b[\s\S]{0,100}\b(?:retry|repeat|return)\b",
            blob,
        )
    )
    return (branching and (conditional or parallel)) or (cyclic and loop)


def flow_as_steps(block: DiagramBlock) -> BulletsBlock:
    """Keep the block identity and every node's complete text when declining a flowchart."""
    return BulletsBlock(
        **block.model_dump(include={"id", "slot_id", "locked", "style"}),
        items=[
            f"{index}. {node.title}" + (f"\n{node.desc}" if node.desc else "")
            for index, node in enumerate(block.nodes, start=1)
        ],
    )


def enforce_text_flow_policy(slide: Slide, *, context: Sequence[str]) -> Slide:
    return slide.model_copy(
        update={
            "blocks": [
                flow_as_steps(block)
                if isinstance(block, DiagramBlock)
                and block.diagram_type in {"flow", "cycle"}
                and not should_keep_flow_diagram(block.nodes, block.edges, context=context or ("",))
                else block
                for block in slide.blocks
            ]
        }
    )


def is_numbered_steps(block) -> bool:
    return (
        isinstance(block, BulletsBlock)
        and bool(block.items)
        and all(item.startswith(f"{index}. ") for index, item in enumerate(block.items, 1))
    )


def compact_flow_nodes(
    nodes: Sequence[DiagramNode],
    *,
    title_limit: int = 14,
    desc_limit: int = 24,
    max_nodes: int = 9,
) -> list[DiagramNode]:
    return list(nodes)


def card_items_from_flow_nodes(
    nodes: Sequence[DiagramNode],
    *,
    title_limit: int = 18,
    desc_limit: int = 56,
    max_items: int = 6,
) -> list[CardItem]:
    items: list[CardItem] = []
    for node in nodes:
        title = node.title.strip()
        desc = node.desc.strip()
        if not desc and title != node.title.strip():
            desc = node.title.strip()
        items.append(
            CardItem(
                title=title or node.title,
                desc=desc,
            )
        )
    return items


def compact_card_items(
    items: Sequence[CardItem],
    *,
    title_limit: int = 18,
    desc_limit: int = 56,
    max_items: int = 6,
) -> list[CardItem]:
    return [
        item.model_copy(
            update={
                "title": item.title.strip(),
                "desc": item.desc.strip(),
            }
        )
        for item in items
    ]


def _clean_step_title(text: str) -> str:
    value = " ".join(text.split()).strip()
    for prefix in _STEP_PREFIXES:
        if value.startswith(prefix):
            value = value[len(prefix) :].lstrip("：: -—")
            break
    head, sep, tail = value.partition("：")
    if not sep:
        head, sep, tail = value.partition(":")
    if sep and tail and len(head) <= 5:
        value = tail.strip()
    for delimiter in ("。", "；", ";", "，", ","):
        value = value.split(delimiter, 1)[0].strip()
    return value


def _compact_text(text: str, limit: int) -> str:
    value = " ".join(text.split())
    if len(value) <= limit:
        return value
    return value[: max(1, limit - 1)].rstrip() + "…"
