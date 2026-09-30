from __future__ import annotations

from collections.abc import Sequence

from app.domain.content import CardItem, DiagramEdge, DiagramNode

COMPLEX_FLOW_KEYWORDS = (
    "故障",
    "预警",
    "分流",
    "分类",
    "分支",
    "并行",
    "汇聚",
    "判断",
    "条件",
    "决策",
    "审批",
    "应急",
    "处置",
    "排查",
    "恢复",
    "复盘",
    "上报",
    "异常",
    "失败",
    "成功",
    "通过",
    "驳回",
    "回退",
    "派单",
    "流转",
)

SIMPLE_STEP_KEYWORDS = (
    "步骤",
    "路径",
    "推进",
    "路线",
    "阶段",
    "第一步",
    "第二步",
    "第三步",
    "第四步",
    "第五步",
    "前两步",
    "最后",
    "先",
    "再",
    "然后",
)

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
    outgoing: dict[str, int] = {}
    incoming: dict[str, int] = {}
    for edge in edges:
        outgoing[edge.source] = outgoing.get(edge.source, 0) + 1
        incoming[edge.target] = incoming.get(edge.target, 0) + 1
    return any(count > 1 for count in outgoing.values()) or any(
        count > 1 for count in incoming.values()
    )


def should_keep_flow_diagram(
    nodes: Sequence[DiagramNode],
    edges: Sequence[DiagramEdge],
    *,
    context: Sequence[str] = (),
) -> bool:
    """Only keep flowcharts for real branching, decisions or exception handling."""
    if len(nodes) < 3:
        return False
    blob = _text_blob(nodes, edges, context)
    if has_branching_edges(edges):
        return not _looks_like_simple_steps(blob, nodes)
    if _looks_like_simple_steps(blob, nodes):
        return False
    if len(nodes) < 4:
        return False
    if any(keyword in blob for keyword in COMPLEX_FLOW_KEYWORDS):
        return True
    return False


def compact_flow_nodes(
    nodes: Sequence[DiagramNode],
    *,
    title_limit: int = 14,
    desc_limit: int = 24,
    max_nodes: int = 9,
) -> list[DiagramNode]:
    result: list[DiagramNode] = []
    for node in nodes[:max_nodes]:
        title = _clean_step_title(node.title)
        desc = node.desc.strip()
        result.append(
            node.model_copy(
                update={
                    "title": _compact_text(title or node.title, title_limit),
                    "desc": _compact_text(desc, desc_limit),
                }
            )
        )
    return result


def card_items_from_flow_nodes(
    nodes: Sequence[DiagramNode],
    *,
    title_limit: int = 18,
    desc_limit: int = 56,
    max_items: int = 6,
) -> list[CardItem]:
    items: list[CardItem] = []
    for node in nodes[:max_items]:
        title = _clean_step_title(node.title)
        desc = node.desc.strip()
        if not desc and title != node.title.strip():
            desc = node.title.strip()
        items.append(
            CardItem(
                title=_compact_text(title or node.title, title_limit),
                desc=_compact_text(desc, desc_limit),
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
                "title": _compact_text(item.title, title_limit),
                "desc": _compact_text(item.desc, desc_limit),
            }
        )
        for item in items[:max_items]
    ]


def _text_blob(
    nodes: Sequence[DiagramNode],
    edges: Sequence[DiagramEdge],
    context: Sequence[str],
) -> str:
    return " ".join(
        [
            *context,
            *[node.title for node in nodes],
            *[node.desc for node in nodes],
            *[edge.label or "" for edge in edges],
        ]
    )


def _looks_like_simple_steps(blob: str, nodes: Sequence[DiagramNode]) -> bool:
    if any(keyword in blob for keyword in SIMPLE_STEP_KEYWORDS):
        return True
    stepish = 0
    for node in nodes:
        title = node.title.strip()
        if title.startswith(_STEP_PREFIXES) or title.startswith("第"):
            stepish += 1
    return stepish >= max(2, len(nodes) // 2)


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
