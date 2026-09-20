"""Reviewed composition families: shared titles, evidence area and source footer."""

from __future__ import annotations

import json
from functools import lru_cache

from app.core.paths import SHARED_DIR
from app.domain.content import (
    Block,
    CalloutBlock,
    ChartBlock,
    DiagramBlock,
    DiagramEdge,
    DiagramNode,
    KpiBlock,
    Slide,
)
from app.domain.evidence import comparable_categories, comparable_series
from app.domain.flex_layout import FlexContainer, FlexLeaf, FlexNode
from app.domain.outline import OutlinePageDraft
from app.domain.slide_geometry import placed_by_block_id


@lru_cache
def report_layouts() -> dict:
    return json.loads((SHARED_DIR / "report-layouts.json").read_text(encoding="utf-8"))


def layout_family(page: OutlinePageDraft) -> str:
    if page.page_role in {"cover", "toc", "section"}:
        return "cover"
    if page.evidence_kind != "narrative":
        return page.evidence_kind
    return page.narrative_role


def bind_planned_evidence(
    slide: Slide, page: OutlinePageDraft, source_labels: dict[str, str] | None = None
) -> Slide:
    """图表与指标值由已校验的证据组装，模型仅负责解读。"""
    blocks = list(slide.blocks)
    series = comparable_series(page.evidence)
    categories = comparable_categories(page.evidence)
    if page.evidence_kind in {"trend", "chart", "composition", "comparison"} and (
        series or categories
    ):
        blocks = [b for b in blocks if b.type != "chart"]
        block_id = _unique_id("report-chart", blocks)
        chart_type = _chart_type_for(page, series=series, categories=categories)
        source_rows = series if chart_type == "line" else categories
        if not source_rows:
            source_rows = series or categories
        blocks.append(
            ChartBlock(
                id=block_id,
                slot_id="visual",
                chart_type=chart_type,
                categories=[
                    e.period if chart_type == "line" else e.category for e in source_rows
                ],
                unit=source_rows[0].unit,
                series=[
                    {
                        "name": source_rows[0].metric,
                        "values": [
                            float(e.value.replace(",", "").rstrip("%％")) for e in source_rows
                        ],
                    }
                ],
            )
        )
    if page.evidence_kind in {"flow", "timeline"}:
        blocks = [b for b in blocks if b.type != "diagram"]
        nodes = _diagram_nodes(page)
        if len(nodes) >= 2:
            block_id = _unique_id("report-diagram", blocks)
            blocks.append(
                DiagramBlock(
                    id=block_id,
                    slot_id="visual",
                    diagram_type="timeline" if page.evidence_kind == "timeline" else "flow",
                    nodes=nodes,
                    edges=[
                        DiagramEdge(source=left.id, target=right.id)
                        for left, right in zip(nodes, nodes[1:], strict=False)
                    ],
                )
            )
    if not any(b.type in {"chart", "diagram", "image"} for b in blocks):
        diagram_kind = _semantic_diagram_kind(page)
        nodes = _diagram_nodes(page)
        if diagram_kind and len(nodes) >= 3:
            block_id = _unique_id("semantic-diagram", blocks)
            blocks.append(
                DiagramBlock(
                    id=block_id,
                    slot_id="visual",
                    diagram_type=diagram_kind,
                    nodes=nodes,
                    edges=[
                        DiagramEdge(source=left.id, target=right.id)
                        for left, right in zip(nodes, nodes[1:], strict=False)
                    ],
                )
            )
    if page.evidence_kind == "kpi":
        metrics = [e for e in page.evidence if e.value and e.metric and e.unit]
        blocks = [b for b in blocks if b.type != "kpi"]
        for index, item in enumerate(metrics):
            value = item.value if item.value.endswith(("%", "％")) else item.value + item.unit
            blocks.append(
                KpiBlock(
                    id=_unique_id(f"report-kpi-{index}", blocks),
                    slot_id=f"kpi_{index + 1}",
                    value=value,
                    label=item.metric,
                    note=" · ".join(filter(None, [item.period, item.scope])),
                )
            )
    if page.evidence:
        references = dict.fromkeys(e.source_ref for e in page.evidence)
        periods = dict.fromkeys(e.period for e in page.evidence if e.period)
        scopes = dict.fromkeys(e.scope for e in page.evidence if e.scope)
        source_text = "来源：" + "；".join(
            (source_labels or {}).get(ref, ref) for ref in references
        )
        source_text += "".join(f" · {'、'.join(values)}" for values in (periods, scopes) if values)
        blocks = [b for b in blocks if not (b.type == "callout" and b.variant == "source")]
        blocks.append(
            CalloutBlock(
                id=_unique_id("report-source", blocks),
                slot_id="source",
                text=source_text,
                variant="source",
            )
        )
    notes = slide.speaker_notes or ""
    if page.evidence:
        notes += "\n\n证据原句：\n" + "\n".join(
            f"[{e.source_ref}] {e.quote}" for e in page.evidence
        )
    return slide.model_copy(update={"blocks": blocks, "speaker_notes": notes})


def _unique_id(base: str, blocks: list[Block]) -> str:
    ids = {b.id for b in blocks}
    candidate = base
    while candidate in ids:
        candidate += "-x"
    return candidate


def compose_report_slide(slide: Slide, page: OutlinePageDraft) -> Slide:
    """只在生成期编排；手工编辑不会经过这里，保留用户排版。"""
    blocks = list(slide.blocks)
    texts = [b for b in blocks if b.type == "text"]
    placed = placed_by_block_id(slide)
    styled_title = next(
        (b for b in texts if b.id in placed and placed[b.id].text_style in {"title", "display"}),
        None,
    )
    title = next(
        (
            b
            for b in texts
            if b.slot_id in {"title", "heading", "display"}
            or b.id == "title"
            or b.id.endswith("-title")
        ),
        styled_title or (texts[0] if texts else None),
    )
    footers = [b for b in blocks if b.type == "callout" and b.variant == "source"]
    body = [b for b in blocks if b != title and b not in footers]

    def leaf(block: Block, style: str | None = None) -> FlexLeaf:
        return FlexLeaf(
            id=f"leaf-{block.id}",
            block_id=block.id,
            text_style=style
            or ("body" if block.type == "text" else "bullet" if block.type == "bullets" else None),
        )

    def column(items: list[Block], name: str) -> FlexContainer:
        return FlexContainer(type="column", id=name, gap_pt=16, children=[leaf(b) for b in items])

    family = layout_family(page)
    composition = report_layouts().get(family, report_layouts()["supporting"])["composition"]
    children: list[FlexNode] = []
    if title:
        children.append(leaf(title, "display" if page.page_role == "cover" else "title"))
    visuals = [b for b in body if b.type in {"chart", "diagram", "image"}]
    metrics = [b for b in body if b.type == "kpi"]
    if visuals and len(body) > len(visuals):
        children.append(
            FlexContainer(
                type="row",
                id="evidence-and-insight",
                ratios=[67, 33],
                gap_pt=28,
                children=[
                    column(visuals, "evidence"),
                    column([b for b in body if b not in visuals], "insight"),
                ],
            )
        )
    elif composition == "metrics" and metrics:
        for start in range(0, len(metrics), 3):
            row = metrics[start : start + 3]
            children.append(
                FlexContainer(
                    type="row", id=f"metrics-{start}", gap_pt=24, children=[leaf(b) for b in row]
                )
            )
        children.extend(leaf(b) for b in body if b not in metrics)
    elif composition == "columns" and 2 <= len(body) <= 4:
        children.append(
            FlexContainer(type="row", id="comparison", gap_pt=28, children=[leaf(b) for b in body])
        )
    elif composition == "timeline" and len(body) > 1:
        children.append(
            FlexContainer(
                type="row" if len(body) <= 4 else "column",
                id="timeline",
                preset="numbered_steps" if len(body) <= 4 else "timeline",
                gap_pt=16,
                children=[leaf(b) for b in body],
            )
        )
    else:
        children.extend(leaf(b) for b in body)
    children.extend(leaf(b, "caption") for b in footers)
    tree = FlexContainer(type="column", id=f"report-{family}", gap_pt=20, children=children)
    return slide.model_copy(update={"layout_tree": tree})


def _chart_type_for(page: OutlinePageDraft, *, series, categories) -> str:
    requested = page.visual_type
    if requested in {"line", "column", "bar", "pie"}:
        if requested == "line" and series:
            return requested
        if requested != "line" and categories:
            return requested
    if page.evidence_kind == "trend" and series:
        return "line"
    if page.evidence_kind == "composition" and categories:
        return "pie"
    if page.evidence_kind == "comparison" and categories:
        return "bar"
    if categories:
        return "bar" if any(len(item.category) > 8 for item in categories) else "column"
    return "line"


_FLOW_KEYWORDS = (
    "流程",
    "路径",
    "机制",
    "驱动",
    "驱动力",
    "原因",
    "影响",
    "形成",
    "转向",
    "方法",
    "如何",
    "怎么",
    "步骤",
    "输入",
    "输出",
)
_TIMELINE_KEYWORDS = (
    "阶段",
    "时间",
    "里程碑",
    "路线图",
    "演进",
    "历程",
    "节奏",
    "变化",
    "趋势",
    "未来",
)
_VISUAL_NARRATIVE_ROLES = {"driver", "risk", "action", "decision"}


def _semantic_diagram_kind(page: OutlinePageDraft) -> str | None:
    """给非数值概念页补结构图，避免所有内容都退化成文字卡片。"""
    if page.page_role in {"cover", "toc", "section"} or len(page.key_points) < 3:
        return None
    blob = " ".join([page.title, page.objective, page.key_message, *page.key_points])
    if page.narrative_role in _VISUAL_NARRATIVE_ROLES:
        return "flow"
    if any(word in blob for word in _TIMELINE_KEYWORDS):
        return "timeline"
    if any(word in blob for word in _FLOW_KEYWORDS):
        return "flow"
    return None


def _diagram_nodes(page: OutlinePageDraft) -> list[DiagramNode]:
    nodes: list[DiagramNode] = []
    for index, point in enumerate(page.key_points[:6], start=1):
        title, _, desc = point.partition("：")
        if not desc:
            title, _, desc = point.partition(":")
        nodes.append(
            DiagramNode(
                id=f"step-{index}",
                title=title.strip() or f"步骤 {index}",
                desc=desc.strip(),
                status="active" if index == 1 else "default",
            )
        )
    return nodes
