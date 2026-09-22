"""Reviewed composition families: shared titles, evidence area and source footer."""

from __future__ import annotations

import json
from functools import lru_cache

from app.core.paths import SHARED_DIR
from app.domain.content import (
    Block,
    CalloutBlock,
    CardsBlock,
    ChartBlock,
    ComboChartBlock,
    DiagramBlock,
    DiagramEdge,
    DiagramNode,
    FinancialTableBlock,
    FinancialTableRow,
    KpiBlock,
    Slide,
    TableBlock,
    WaterfallBlock,
    WaterfallItem,
)
from app.domain.evidence import comparable_categories, comparable_series, numeric_value
from app.domain.flex_layout import FlexContainer, FlexLeaf, FlexNode
from app.domain.mermaid import ensure_mermaid
from app.domain.outline import OutlinePageDraft
from app.domain.slide_geometry import placed_by_block_id
from app.domain.topic_visuals import evidence_kind_for_visual


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
    slide: Slide,
    page: OutlinePageDraft,
    source_labels: dict[str, str] | None = None,
    *,
    topic_mode: bool = False,
) -> Slide:
    """图表与指标值由已校验的证据组装，模型仅负责解读。"""
    blocks = list(slide.blocks)
    series = comparable_series(page.evidence)
    categories = comparable_categories(page.evidence)
    evidence_kind = page.evidence_kind
    requested_kind = evidence_kind_for_visual(page.visual_type)
    if requested_kind in {"flow", "timeline"}:
        # 流程/时间线是结构表达，不依赖数值证据；显式视觉选择应覆盖
        # 模型可能返回的 narrative/table 标记，但不生成来源外的数据。
        evidence_kind = requested_kind
    if topic_mode and page.visual_type != "auto":
        evidence_kind = requested_kind or evidence_kind
        # 主题模式的视觉选择是页面主视觉；避免模型额外塞入图片把图表/流程挤成窄条。
        blocks = [b for b in blocks if b.type != "image"]
    requested_visual = (
        page.visual_type
        if topic_mode
        or page.visual_type in {"financial_table", "waterfall", "combo_chart"}
        else "auto"
    )
    effective_page = page.model_copy(
        update={"evidence_kind": evidence_kind, "visual_type": requested_visual}
    )
    if evidence_kind in {"trend", "chart", "composition", "comparison"} and (
        series or categories
    ):
        blocks = [b for b in blocks if b.type != "chart"]
        block_id = _unique_id("report-chart", blocks)
        chart_type = _chart_type_for(effective_page, series=series, categories=categories)
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
    if page.visual_type == "financial_table":
        financial_table = _financial_table_from_evidence(page.evidence, block_id="report-table")
        if financial_table is not None:
            blocks = [b for b in blocks if b.type not in {"table", "chart", "image"}]
            blocks.append(financial_table)
    elif page.visual_type == "waterfall":
        waterfall = _waterfall_from_evidence(page.evidence, block_id="report-waterfall")
        if waterfall is not None:
            blocks = [b for b in blocks if b.type not in {"chart", "image"}]
            blocks.append(waterfall)
    elif page.visual_type == "combo_chart":
        combo = _combo_from_evidence(page.evidence, block_id="report-combo")
        if combo is not None:
            blocks = [b for b in blocks if b.type not in {"chart", "image"}]
            blocks.append(combo)
    if evidence_kind in {"flow", "timeline"}:
        blocks = [b for b in blocks if b.type != "diagram"]
        nodes = _diagram_nodes(page, blocks=blocks)
        if len(nodes) >= 2:
            edges, direction = _diagram_edges_and_direction(page, nodes, evidence_kind)
            block_id = _unique_id("report-diagram", blocks)
            blocks.append(
                DiagramBlock(
                    id=block_id,
                    slot_id="visual",
                    diagram_type="timeline" if evidence_kind == "timeline" else "flow",
                    mermaid=ensure_mermaid(
                        None,
                        "timeline" if evidence_kind == "timeline" else "flow",
                        nodes,
                        edges,
                        direction=direction,
                    ),
                    nodes=nodes,
                    edges=edges,
                )
            )
    if not any(
        b.type
        in {"chart", "diagram", "image", "financial_table", "waterfall", "combo_chart"}
        for b in blocks
    ):
        diagram_kind = _semantic_diagram_kind(page)
        nodes = _diagram_nodes(page, blocks=blocks)
        if diagram_kind and len(nodes) >= 2:
            edges, direction = _diagram_edges_and_direction(page, nodes, diagram_kind)
            block_id = _unique_id("semantic-diagram", blocks)
            blocks.append(
                DiagramBlock(
                    id=block_id,
                    slot_id="visual",
                    diagram_type=diagram_kind,
                    mermaid=ensure_mermaid(
                        None,
                        diagram_kind,
                        nodes,
                        edges,
                        direction=direction,
                    ),
                    nodes=nodes,
                    edges=edges,
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


def _financial_table_from_evidence(
    evidence: list,
    *,
    block_id: str,
) -> FinancialTableBlock | None:
    numeric = [item for item in evidence if item.value and numeric_value(item.value) is not None]
    if len(numeric) < 2:
        return None
    periods = list(dict.fromkeys(item.period for item in numeric if item.period))
    categories = list(dict.fromkeys(item.category for item in numeric if item.category))
    columns = periods if len(periods) >= 2 else categories
    if len(columns) < 2:
        return None

    use_periods = len(periods) >= 2
    grouped: dict[str, dict[str, str]] = {}
    for item in numeric:
        label = item.metric if use_periods else item.category
        column = item.period if use_periods else item.category
        if not label or not column:
            continue
        grouped.setdefault(label, {})[column] = item.value
    rows = [
        FinancialTableRow(label=label, values=[values.get(column, "") for column in columns])
        for label, values in grouped.items()
    ]
    if not rows:
        return None
    return FinancialTableBlock(
        id=block_id,
        slot_id="visual",
        unit=numeric[0].unit or None,
        columns=columns,
        rows=rows[:8],
        highlight_columns=[len(columns) - 1],
    )


def _waterfall_from_evidence(evidence: list, *, block_id: str) -> WaterfallBlock | None:
    numeric = [item for item in evidence if item.value and numeric_value(item.value) is not None]
    if len(numeric) < 2:
        return None
    selected = numeric[:8]
    items = []
    for index, item in enumerate(selected):
        value = float(numeric_value(item.value) or 0)
        kind = "start" if index == 0 else "increase" if value >= 0 else "decrease"
        if index == len(selected) - 1 and len(selected) >= 3:
            kind = "total"
        items.append(
            WaterfallItem(
                label=item.metric or item.category or f"项目 {index + 1}",
                value=value,
                kind=kind,
            )
        )
    return WaterfallBlock(
        id=block_id,
        slot_id="visual",
        unit=selected[0].unit or None,
        items=items,
    )


def _combo_from_evidence(evidence: list, *, block_id: str) -> ComboChartBlock | None:
    numeric = [item for item in evidence if item.value and item.metric and item.period]
    metrics = list(dict.fromkeys(item.metric for item in numeric))
    periods = list(dict.fromkeys(item.period for item in numeric))
    if len(metrics) < 2 or len(periods) < 2:
        return None
    series: list[tuple[str, list[float]]] = []
    for metric in metrics[:3]:
        values = {
            item.period: float(numeric_value(item.value) or 0)
            for item in numeric
            if item.metric == metric
        }
        if all(period in values for period in periods):
            series.append((metric, [values[period] for period in periods]))
    if len(series) < 2:
        return None
    return ComboChartBlock(
        id=block_id,
        slot_id="visual",
        categories=periods,
        bars=[{"name": series[0][0], "values": series[0][1]}],
        lines=[{"name": name, "values": values} for name, values in series[1:]],
        unit=numeric[0].unit or None,
    )


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
    visuals = [
        b
        for b in body
        if b.type
        in {"chart", "diagram", "image", "financial_table", "waterfall", "combo_chart"}
    ]
    family = layout_family(page)
    composition = report_layouts().get(family, report_layouts()["supporting"])["composition"]

    body, hidden_notes = _curate_report_body(body, page, visuals)
    visuals = [
        b
        for b in body
        if b.type
        in {"chart", "diagram", "image", "financial_table", "waterfall", "combo_chart"}
    ]
    insight_blocks = [b for b in body if b not in visuals]

    visual_type = _effective_visual_type(page, visuals)
    diagram = next((b for b in visuals if b.type == "diagram"), None)
    chart = next((b for b in visuals if b.type == "chart"), None)
    advanced = next(
        (
            b
            for b in visuals
            if b.type in {"financial_table", "waterfall", "combo_chart"}
        ),
        None,
    )
    tree = _compose_report_tree(
        title=title,
        body=body,
        visuals=visuals,
        insight_blocks=insight_blocks,
        footers=footers,
        page=page,
        family=family,
        composition=composition,
        visual_type=visual_type,
        diagram=diagram,
        chart=chart,
        advanced=advanced,
    )
    kept_ids = {block.id for block in ([title] if title else []) + body + footers}
    kept_blocks = [block for block in blocks if block.id in kept_ids]
    speaker_notes = _append_hidden_notes(slide.speaker_notes, hidden_notes)
    return slide.model_copy(
        update={"blocks": kept_blocks, "layout_tree": tree, "speaker_notes": speaker_notes}
    )


def _compose_report_tree(
    *,
    title: Block | None,
    body: list[Block],
    visuals: list[Block],
    insight_blocks: list[Block],
    footers: list[Block],
    page: OutlinePageDraft,
    family: str,
    composition: str,
    visual_type: str,
    diagram: Block | None,
    chart: Block | None,
    advanced: Block | None,
) -> FlexContainer:
    if diagram is not None and visual_type in {"flow", "timeline"}:
        return _visual_report_tree(
            title=title,
            visual=diagram,
            insight_blocks=insight_blocks,
            footers=footers,
            page=page,
            family=family,
            insight_id="structure-insight",
        )
    if chart is not None:
        if any(block.type in {"cards", "table", "kpi"} for block in insight_blocks):
            return _image_support_tree(
                title=title,
                visuals=[chart],
                support=insight_blocks,
                footers=footers,
                page=page,
                family=family,
            )
        return _visual_report_tree(
            title=title,
            visual=chart,
            insight_blocks=insight_blocks,
            footers=footers,
            page=page,
            family=family,
            insight_id="chart-insight",
        )
    if advanced is not None:
        return _visual_report_tree(
            title=title,
            visual=advanced,
            insight_blocks=insight_blocks,
            footers=footers,
            page=page,
            family=family,
            insight_id="evidence-insight",
        )
    if visuals and insight_blocks:
        return _image_support_tree(
            title=title,
            visuals=visuals,
            support=insight_blocks,
            footers=footers,
            page=page,
            family=family,
        )
    if visuals:
        return _visual_report_tree(
            title=title,
            visual=visuals[0],
            insight_blocks=visuals[1:],
            footers=footers,
            page=page,
            family=family,
            insight_id="visual-stack",
        )

    metrics = [block for block in body if block.type == "kpi"]
    if composition == "metrics" and metrics:
        return _metrics_tree(title=title, body=body, metrics=metrics, footers=footers, page=page)
    if (
        composition == "columns"
        and 2 <= len(body) <= 4
        and not all(block.type in {"text", "bullets", "callout"} for block in body)
        and not any(block.type in {"cards", "table", "kpi"} for block in body)
    ):
        return _row_report_tree(title=title, body=body, footers=footers, page=page, tree_id="columns")
    if composition == "timeline" and len(body) > 1:
        return _timeline_tree(title=title, body=body, footers=footers, page=page)
    return _text_report_tree(title=title, body=body, footers=footers, page=page, family=family)


def _visual_report_tree(
    *,
    title: Block | None,
    visual: Block,
    insight_blocks: list[Block],
    footers: list[Block],
    page: OutlinePageDraft,
    family: str,
    insight_id: str,
) -> FlexContainer:
    children = _header_nodes(title, page)
    stage_children: list[FlexNode] = [_leaf(visual, grow=1.0, bleed=True)]
    overlay_children: list[FlexNode] = []
    if insight_blocks or footers:
        overlay_children.append(_spacer("spacer-visual-overlay-top", grow=3.0))
        if insight_blocks:
            overlay_children.append(_column(insight_blocks, insight_id, grow=0.55))
        overlay_children.extend(_footer_nodes(footers))
    if overlay_children:
        stage_children.append(
            FlexContainer(
                type="column",
                id=f"{insight_id}-overlay",
                gap_pt=8,
                grow=1.0,
                children=overlay_children,
            )
        )
    children.append(
        FlexContainer(
            type="overlay",
            id=f"visual-stage-{family}",
            gap_pt=0,
            grow=3.2,
            children=stage_children,
        )
    )
    return FlexContainer(type="column", id=f"visual-{family}", gap_pt=10, children=children)


def _image_support_tree(
    *,
    title: Block | None,
    visuals: list[Block],
    support: list[Block],
    footers: list[Block],
    page: OutlinePageDraft,
    family: str,
) -> FlexContainer:
    children = _header_nodes(title, page)
    children.append(
        FlexContainer(
            type="row",
            id="image-support-main",
            ratios=[58, 42],
            gap_pt=28,
            grow=2.4,
            children=[
                _column(visuals, "visual-pane"),
                _column(support, "support-pane"),
            ],
        )
    )
    children.extend(_footer_nodes(footers))
    return FlexContainer(type="column", id=f"image-support-{family}", gap_pt=16, children=children)


def _metrics_tree(
    *,
    title: Block | None,
    body: list[Block],
    metrics: list[Block],
    footers: list[Block],
    page: OutlinePageDraft,
) -> FlexContainer:
    children = _header_nodes(title, page)
    for start in range(0, len(metrics), 3):
        row = metrics[start : start + 3]
        children.append(
            FlexContainer(
                type="row",
                id=f"metrics-{start}",
                gap_pt=24,
                grow=0.9,
                children=[_leaf(block) for block in row],
            )
        )
    children.extend(_leaf(block) for block in body if block not in metrics)
    children.extend(_footer_nodes(footers))
    return FlexContainer(type="column", id="metrics-report", gap_pt=16, children=children)


def _row_report_tree(
    *,
    title: Block | None,
    body: list[Block],
    footers: list[Block],
    page: OutlinePageDraft,
    tree_id: str,
) -> FlexContainer:
    children = _header_nodes(title, page)
    children.append(
        FlexContainer(
            type="row",
            id=tree_id,
            gap_pt=28,
            grow=2.0,
            children=[_leaf(block) for block in body],
        )
    )
    children.extend(_footer_nodes(footers))
    return FlexContainer(type="column", id=f"{tree_id}-report", gap_pt=16, children=children)


def _timeline_tree(
    *,
    title: Block | None,
    body: list[Block],
    footers: list[Block],
    page: OutlinePageDraft,
) -> FlexContainer:
    children = _header_nodes(title, page)
    children.append(
        FlexContainer(
            type="row" if len(body) <= 4 else "column",
            id="timeline",
            preset="numbered_steps" if len(body) <= 4 else "timeline",
            gap_pt=16,
            grow=2.0,
            children=[_leaf(block) for block in body],
        )
    )
    children.extend(_footer_nodes(footers))
    return FlexContainer(type="column", id="timeline-report", gap_pt=16, children=children)


def _text_report_tree(
    *,
    title: Block | None,
    body: list[Block],
    footers: list[Block],
    page: OutlinePageDraft,
    family: str,
) -> FlexContainer:
    children = _header_nodes(title, page)
    children.extend(_leaf(block) for block in body)
    children.extend(_footer_nodes(footers))
    return FlexContainer(type="column", id=f"text-{family}", gap_pt=18, children=children)


def _header_nodes(title: Block | None, page: OutlinePageDraft) -> list[FlexNode]:
    if title is None:
        return []
    return [
        _leaf(
            title,
            "display" if page.page_role == "cover" else "title",
            grow=0.42 if page.page_role != "cover" else 0.8,
        )
    ]


def _footer_nodes(footers: list[Block]) -> list[FlexNode]:
    return [_leaf(block, "caption", grow=0.18) for block in footers]


def _spacer(node_id: str, *, grow: float) -> FlexContainer:
    return FlexContainer(type="column", id=node_id, children=[], gap_pt=0, grow=grow)


def _column(items: list[Block], name: str, *, grow: float = 1.0) -> FlexContainer:
    return FlexContainer(
        type="column",
        id=name,
        gap_pt=14,
        grow=grow,
        children=[_leaf(block) for block in items],
    )


def _leaf(
    block: Block,
    style: str | None = None,
    *,
    grow: float | None = None,
    bleed: bool = False,
) -> FlexLeaf:
    return FlexLeaf(
        id=f"leaf-{block.id}",
        block_id=block.id,
        grow=1.0 if grow is None else grow,
        bleed=bleed,
        text_style=style
        or ("body" if block.type == "text" else "bullet" if block.type == "bullets" else None),
    )


def _effective_visual_type(page: OutlinePageDraft, visuals: list[Block]) -> str:
    if page.visual_type != "auto":
        return page.visual_type
    chart = next((block for block in visuals if isinstance(block, ChartBlock)), None)
    if chart is not None:
        return chart.chart_type
    diagram = next((block for block in visuals if isinstance(block, DiagramBlock)), None)
    if diagram is not None:
        return diagram.diagram_type
    return "image"


def _curate_report_body(
    body: list[Block], page: OutlinePageDraft, visuals: list[Block]
) -> tuple[list[Block], list[str]]:
    """按页面主视觉裁掉生成期无法共存的表达。

    AI 可以同时返回 cards、table、长正文和视觉块，但一页的版式不能无条件
    接受这些块。这里是生成期的确定性收口；真实文档的图表数值仍由
    ``bind_planned_evidence`` 绑定，绝不会因为裁剪而补造数据。
    """
    chart = next((block for block in visuals if isinstance(block, ChartBlock)), None)
    advanced = next(
        (
            block
            for block in visuals
            if isinstance(block, (FinancialTableBlock, WaterfallBlock, ComboChartBlock))
        ),
        None,
    )
    diagram = next((block for block in visuals if isinstance(block, DiagramBlock)), None)
    visual_type = _effective_visual_type(page, visuals)

    if diagram is not None and visual_type in {"flow", "timeline"}:
        compact = _compact_diagram(diagram)
        # 结构图页不再同时承载表格或第二套卡片表达，但保留一段
        # 压缩后的关键说明，避免为了防止挤压而把正文全部丢掉。
        support, hidden = _visual_support_blocks(
            [
                block
                for block in body
                if block not in visuals and block.type not in {"cards", "table", "kpi", "callout"}
            ],
            limit=1,
            text_limit=76,
            max_source_chars=90,
        )
        return [compact, *support], hidden

    if chart is not None:
        if chart.chart_type == "pie" or visual_type == "pie":
            cards = next((block for block in body if isinstance(block, CardsBlock)), None)
            if cards is not None:
                return [chart, _limit_cards(cards, 3)], []
        support, hidden = _visual_support_blocks(
            [
                block
                for block in body
                if block not in visuals and block.type not in {"cards", "table", "kpi", "callout"}
            ],
            limit=1,
            text_limit=76,
            max_source_chars=90,
        )
        return [chart, *support], hidden

    if advanced is not None:
        support, hidden = _visual_support_blocks(
            [
                block
                for block in body
                if block not in visuals
                and block.type
                not in {"cards", "table", "chart", "diagram", "image", "kpi", "callout"}
            ],
            limit=1,
            text_limit=72,
            max_source_chars=90,
        )
        return [advanced, *support], hidden

    if page.evidence_kind in {"actions", "table"} or page.narrative_role in {"action", "risk"}:
        structured = _choose_structured_block(body, page)
        support = _short_support_blocks(
            [
                block
                for block in body
                if block is not structured
                and block.type not in {"cards", "table", "chart", "diagram", "image", "kpi"}
            ],
            limit=1,
        )
        return [block for block in [structured, *support] if block is not None], []

    if visuals:
        support, hidden = _visual_support_blocks(
            [block for block in body if block not in visuals],
            limit=1,
            text_limit=84,
            max_source_chars=140,
        )
        return [*visuals, *support], hidden
    return body, []


def _visual_support_blocks(
    blocks: list[Block],
    *,
    limit: int,
    text_limit: int,
    max_source_chars: int,
) -> tuple[list[Block], list[str]]:
    """视觉页只保留短洞察；长解释进入讲稿，避免形成固定四段挤压。"""
    visible: list[Block] = []
    hidden: list[str] = []
    for block in blocks:
        note = _note_for_hidden_block(block)
        if len(visible) >= limit:
            if note:
                hidden.append(note)
            continue
        if block.type == "text":
            text = " ".join(block.text.split())
            if len(text) <= max_source_chars:
                visible.append(block.model_copy(update={"text": _compact_text(text, text_limit)}))
            elif note:
                hidden.append(note)
            continue
        if block.type == "bullets":
            joined = "；".join(item.strip() for item in block.items if item.strip())
            if len(joined) <= max_source_chars:
                visible.append(
                    block.model_copy(
                        update={
                            "items": [
                                _compact_text(item, max(24, text_limit // 2))
                                for item in block.items[:2]
                            ]
                        }
                    )
                )
            elif note:
                hidden.append(note)
            continue
        if note:
            hidden.append(note)
    return visible, hidden


def _short_support_blocks(blocks: list[Block], *, limit: int) -> list[Block]:
    result: list[Block] = []
    for block in blocks:
        if len(result) >= limit:
            break
        if block.type == "text":
            result.append(block.model_copy(update={"text": _compact_text(block.text, 180)}))
        elif block.type == "bullets":
            result.append(
                block.model_copy(
                    update={
                        "items": [
                            _compact_text(item, 90)
                            for item in block.items[:3]
                        ]
                    }
                )
            )
    return result


def _note_for_hidden_block(block: Block) -> str | None:
    if block.type == "text":
        text = " ".join(block.text.split())
        return text or None
    if block.type == "bullets":
        items = [item.strip() for item in block.items if item.strip()]
        return "；".join(items) or None
    if block.type == "cards":
        items = [
            "：".join(part for part in [item.title.strip(), item.desc.strip()] if part)
            for item in block.items
        ]
        return "；".join(item for item in items if item) or None
    if block.type == "table":
        rows = [" / ".join(cell.strip() for cell in row if cell.strip()) for row in block.rows[:6]]
        return "；".join(row for row in rows if row) or None
    return None


def _append_hidden_notes(current: str | None, notes: list[str]) -> str | None:
    notes = [note for note in notes if note]
    if not notes:
        return current
    prefix = (current or "").rstrip()
    extra = "\n".join(f"- {note}" for note in notes)
    section = "未放入画布的补充说明：\n" + extra
    return f"{prefix}\n\n{section}" if prefix else section


def _choose_structured_block(body: list[Block], page: OutlinePageDraft) -> Block | None:
    table = next((block for block in body if isinstance(block, TableBlock)), None)
    cards = next((block for block in body if isinstance(block, CardsBlock)), None)
    if table is None and cards is None:
        return None
    if page.evidence_kind == "table":
        return _limit_table(table) if table is not None else _limit_cards(cards, 4)  # type: ignore[arg-type]
    if page.narrative_role == "risk":
        if cards is not None and len(cards.items) <= 4:
            return _limit_cards(cards, 4)
        return _limit_table(table) if table is not None else _limit_cards(cards, 4)  # type: ignore[arg-type]
    if table is not None and len(table.header) <= 5 and len(table.rows) <= 6:
        return _limit_table(table)
    return _limit_cards(cards, 4) if cards is not None else _limit_table(table)  # type: ignore[arg-type]


def _limit_cards(block: CardsBlock | None, limit: int) -> CardsBlock | None:
    if block is None:
        return None
    items = [
        item.model_copy(
            update={
                "title": _compact_text(item.title, 34),
                "desc": _compact_text(item.desc, 78),
            }
        )
        for item in block.items[:limit]
    ]
    return block.model_copy(update={"items": items})


def _limit_table(block: TableBlock | None) -> TableBlock | None:
    if block is None:
        return None
    header = [_compact_text(value, 24) for value in block.header[:6]]
    rows = [
        [_compact_text(value, 42) for value in row[: len(header)]]
        for row in block.rows[:8]
    ]
    rows = [row + [""] * (len(header) - len(row)) for row in rows]
    return block.model_copy(update={"header": header, "rows": rows})


def _compact_diagram(block: DiagramBlock) -> DiagramBlock:
    nodes = [
        node.model_copy(
            update={
                "title": _compact_text(node.title, 24),
                "desc": _compact_text(node.desc, 48),
            }
        )
        for node in block.nodes[:9]
    ]
    node_ids = {node.id for node in nodes}
    edges = [edge for edge in block.edges if edge.source in node_ids and edge.target in node_ids]
    return block.model_copy(
        update={
            "nodes": nodes,
            "edges": edges,
            "mermaid": ensure_mermaid(
                None,
                block.diagram_type,
                nodes,
                edges,
                direction=_diagram_direction_from_mermaid(block.mermaid),
            ),
        }
    )


def _compact_text(text: str, limit: int) -> str:
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    return text[: max(1, limit - 1)].rstrip() + "…"


def _diagram_direction_from_mermaid(mermaid: str | None) -> str | None:
    if not mermaid:
        return None
    head = mermaid.strip().splitlines()[0].upper()
    if "FLOWCHART TB" in head or "FLOWCHART TD" in head:
        return "TB"
    if "FLOWCHART LR" in head:
        return "LR"
    return None


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
_BRANCH_FLOW_KEYWORDS = (
    "故障",
    "预警",
    "分流",
    "分类",
    "并行",
    "汇聚",
    "应急",
    "处置",
    "审批",
    "排查",
    "恢复",
    "复盘",
    "上报",
)
_VISUAL_NARRATIVE_ROLES = {"driver", "risk", "action", "decision"}


def _semantic_diagram_kind(page: OutlinePageDraft) -> str | None:
    """给非数值概念页补结构图，避免所有内容都退化成文字卡片。"""
    if page.page_role in {"cover", "toc", "section"} or len(page.key_points) < 2:
        return None
    if page.visual_type in {"flow", "timeline"}:
        return page.visual_type
    blob = " ".join([page.title, page.objective, page.key_message, *page.key_points])
    if page.narrative_role in _VISUAL_NARRATIVE_ROLES:
        return "flow"
    if any(word in blob for word in _TIMELINE_KEYWORDS):
        return "timeline"
    if any(word in blob for word in _FLOW_KEYWORDS):
        return "flow"
    return None


def _diagram_nodes(
    page: OutlinePageDraft,
    *,
    blocks: list[Block] | None = None,
) -> list[DiagramNode]:
    structured = _structured_diagram_nodes(page, blocks or [])
    if structured:
        return structured

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


def _diagram_edges_and_direction(
    page: OutlinePageDraft,
    nodes: list[DiagramNode],
    diagram_kind: str,
) -> tuple[list[DiagramEdge], str | None]:
    if diagram_kind == "timeline":
        return _sequential_edges(nodes), "TB"
    if _should_branch_flow(page, nodes) or len(nodes) >= 5:
        return _branch_flow_edges(nodes), "TB"
    return _sequential_edges(nodes), "TB"


def _sequential_edges(nodes: list[DiagramNode]) -> list[DiagramEdge]:
    return [
        DiagramEdge(source=left.id, target=right.id)
        for left, right in zip(nodes, nodes[1:], strict=False)
    ]


def _should_branch_flow(page: OutlinePageDraft, nodes: list[DiagramNode]) -> bool:
    if len(nodes) < 6:
        return False
    blob = " ".join(
        [
            page.title,
            page.objective,
            page.key_message,
            *page.key_points,
            *[node.title for node in nodes],
            *[node.desc for node in nodes],
        ]
    )
    return any(keyword in blob for keyword in _BRANCH_FLOW_KEYWORDS)


def _branch_flow_edges(nodes: list[DiagramNode]) -> list[DiagramEdge]:
    """Default branch/merge topology for incident, approval and dispatch flows."""
    if len(nodes) < 5:
        return _sequential_edges(nodes)
    branch_from_index = 1 if len(nodes) >= 6 else 0
    merge_index = len(nodes) - 3 if len(nodes) >= 6 else len(nodes) - 1
    if merge_index <= branch_from_index + 1:
        return _sequential_edges(nodes)

    edges = []
    if branch_from_index > 0:
        edges.append(DiagramEdge(source=nodes[0].id, target=nodes[branch_from_index].id))
    branch_nodes = nodes[branch_from_index + 1 : merge_index]
    for node in branch_nodes:
        edges.append(DiagramEdge(source=nodes[branch_from_index].id, target=node.id))
        edges.append(DiagramEdge(source=node.id, target=nodes[merge_index].id))
    edges.extend(_sequential_edges(nodes[merge_index:]))
    return edges


def _structured_diagram_nodes(page: OutlinePageDraft, blocks: list[Block]) -> list[DiagramNode]:
    """把模型已经生成的结构化表达转成真正的节点，避免编排时丢内容。"""
    if page.visual_type == "timeline" or page.evidence_kind == "timeline":
        table = next((block for block in blocks if isinstance(block, TableBlock)), None)
        if table is not None and table.rows:
            headers = table.header
            nodes: list[DiagramNode] = []
            for index, row in enumerate(table.rows[:9], start=1):
                values = [value.strip() for value in row]
                title = values[0] if values and values[0] else f"阶段 {index}"
                details = []
                for column, value in enumerate(values[1:], start=1):
                    if not value:
                        continue
                    label = headers[column] if column < len(headers) and headers[column] else ""
                    details.append(f"{label}：{value}" if label else value)
                nodes.append(
                    DiagramNode(
                        id=f"step-{index}",
                        title=title,
                        desc="；".join(details),
                        status="active" if index == 1 else "default",
                    )
                )
            if len(nodes) >= 2:
                return nodes

    if page.visual_type == "flow" or page.evidence_kind == "flow":
        cards = next((block for block in blocks if isinstance(block, CardsBlock)), None)
        if cards is not None and len(cards.items) >= 2:
            return [
                DiagramNode(
                    id=f"step-{index}",
                    title=item.title,
                    desc=item.desc,
                    status="active" if index == 1 else "default",
                )
                for index, item in enumerate(cards.items[:9], start=1)
            ]
    return []
