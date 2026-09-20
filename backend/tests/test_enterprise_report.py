"""Enterprise planning, source fidelity, composition and export regression checks."""

import uuid
from io import BytesIO

import pytest
from pptx import Presentation

from app.domain.content import ChartBlock, Deck, DiagramBlock, Slide, TextBlock
from app.domain.enterprise_layout import bind_planned_evidence, compose_report_slide
from app.domain.enterprise_quality import check_planned_data, check_report_quality
from app.domain.evidence import comparable_series, evidence_problem, prepare_page_plan
from app.domain.flex_layout import FlexContainer, FlexLeaf, iter_leaf_block_ids
from app.domain.outline import DeckBlueprint, EvidenceItem, OutlinePage, ReportBrief
from app.domain.theme import get_theme
from app.render.pptx import render_deck_to_pptx
from app.render.verify import verify_pptx
from app.services.preview import load_preview_status, preview_fingerprint, save_preview_status


def fact(value="120", period="Q1", **changes):
    return EvidenceItem.model_validate(
        {
            "source_ref": "S1:1",
            "quote": f"{period}集团收入{value}万元。",
            "metric": "收入",
            "value": value,
            "unit": "万元",
            "period": period,
            "scope": "集团",
            **changes,
        }
    )


def category_fact(category: str, value: str):
    return fact(
        value=value,
        quote=f"Q1集团收入中{category}{value}万元。",
        period="Q1",
        category=category,
    )


def plan(**changes):
    return OutlinePage.model_validate(
        {
            "title": "收入提升",
            "objective": "说明经营变化",
            "key_points": ["结果", "行动"],
            "layout_id": "chart",
            "evidence_kind": "trend",
            "narrative_role": "performance",
            "key_message": "收入提升",
            "evidence": [fact(), fact("140", "Q2")],
            **changes,
        }
    )


def slide():
    return Slide(
        id="s1",
        layout_id="bullets",
        layout_mode="flex",
        blocks=[
            TextBlock(id="kicker", slot_id="kicker", text="经营复盘"),
            TextBlock(id="heading-xyz", slot_id="heading-xyz", text="收入提升"),
            TextBlock(id="insight", slot_id="insight", text="持续观察经营质量"),
        ],
        layout_tree=FlexContainer(
            type="column",
            id="root",
            children=[
                FlexLeaf(id="l1", block_id="kicker", text_style="caption"),
                FlexLeaf(id="l2", block_id="heading-xyz", text_style="title"),
                FlexLeaf(id="l3", block_id="insight", text_style="body"),
            ],
        ),
    )


@pytest.mark.parametrize(
    "change",
    [
        {"value": "12"},
        {"value": "120%"},
        {"unit": "%"},
        {"metric": "利润"},
        {"period": "Q2"},
        {"scope": "子公司"},
        {"quote": "材料不存在的句子"},
        {"value": "NaN"},
        {"value": "Infinity"},
    ],
)
def test_false_evidence_rejected(change):
    assert evidence_problem(fact(**change), {"S1:1": "Q1集团收入120万元。"})


def test_valid_evidence_and_incompatible_series():
    assert evidence_problem(fact(), {"S1:1": "Q1集团收入120万元。"}) is None
    assert len(comparable_series([fact(), fact("140", "Q2")])) == 2
    assert not comparable_series([fact(), fact("140", "Q2", scope="子公司")])
    assert not comparable_series([fact(), fact("140")])


def test_missing_data_downgrades_without_inventing_metrics():
    result = prepare_page_plan(plan(), {})
    assert result.evidence_kind == "narrative"
    assert result.layout_id == "bullets"
    assert result.evidence == []
    assert result.planning_notes


def test_flow_without_numeric_evidence_keeps_diagram_intent():
    result = prepare_page_plan(
        plan(
            evidence_kind="flow",
            visual_type="flow",
            key_points=["输入：识别问题", "处理：拆解任务", "输出：形成方案"],
            evidence=[],
        ),
        {},
    )

    assert result.evidence_kind == "flow"
    assert result.visual_type == "flow"
    assert not result.planning_notes


def test_composition_keeps_each_block_once_and_title_style():
    result = compose_report_slide(bind_planned_evidence(slide(), plan()), plan())
    assert result.layout_tree.children[0].block_id == "heading-xyz"
    ids = iter_leaf_block_ids(result.layout_tree)
    assert len(ids) == len(set(ids)) == len(result.blocks)
    assert set(ids) == {b.id for b in result.blocks}
    assert not check_planned_data(result, plan())
    chart = next(b for b in result.blocks if b.type == "chart")
    chart.series[0].values[1] = 999
    assert check_planned_data(result, plan())[0].severity == "error"


def test_composition_evidence_defaults_to_pie_chart():
    page = plan(
        evidence_kind="composition",
        visual_type="auto",
        evidence=[category_fact("线上", "60"), category_fact("线下", "40")],
    )
    result = bind_planned_evidence(slide(), page)
    chart = next(b for b in result.blocks if b.type == "chart")

    assert chart.chart_type == "pie"
    assert chart.categories == ["线上", "线下"]
    assert chart.series[0].values == [60.0, 40.0]


def test_comparison_evidence_defaults_to_bar_chart():
    page = plan(
        evidence_kind="comparison",
        visual_type="auto",
        evidence=[category_fact("A方案", "120"), category_fact("B方案", "95")],
    )
    result = bind_planned_evidence(slide(), page)
    chart = next(b for b in result.blocks if b.type == "chart")

    assert chart.chart_type == "bar"
    assert chart.categories == ["A方案", "B方案"]


def test_flow_plan_binds_native_diagram_block():
    page = plan(
        evidence_kind="flow",
        visual_type="flow",
        key_points=["采集：汇总业务输入", "校验：核对口径", "输出：形成汇报"],
        evidence=[],
    )
    result = bind_planned_evidence(slide(), page)
    diagram = next(b for b in result.blocks if b.type == "diagram")

    assert isinstance(diagram, DiagramBlock)
    assert diagram.diagram_type == "flow"
    assert [node.title for node in diagram.nodes] == ["采集", "校验", "输出"]
    assert [(edge.source, edge.target) for edge in diagram.edges] == [
        ("step-1", "step-2"),
        ("step-2", "step-3"),
    ]


def test_qualitative_driver_page_gets_semantic_diagram_fallback():
    page = plan(
        title="背后驱动力：开发方式正在变化",
        evidence_kind="narrative",
        narrative_role="driver",
        key_points=["工具普及：降低重复劳动", "需求变化：业务理解更重要", "协作升级：人机共同交付"],
        evidence=[],
    )
    result = bind_planned_evidence(slide(), page)
    diagram = next(b for b in result.blocks if b.type == "diagram")

    assert diagram.diagram_type == "flow"
    assert [node.title for node in diagram.nodes] == ["工具普及", "需求变化", "协作升级"]


def test_unplanned_chart_rejected_in_fixed_mode_too():
    data = ChartBlock(
        id="chart",
        slot_id="visual",
        chart_type="line",
        categories=["Q1"],
        series=[{"name": "收入", "values": [999]}],
        unit="万元",
    )
    result = Slide(id="fixed", layout_id="chart", blocks=[data])
    assert check_planned_data(result, plan(evidence=[]))


def test_pptx_roundtrip_checks_actual_numeric_values():
    result = compose_report_slide(bind_planned_evidence(slide(), plan()), plan())
    deck = Deck(id="d", title="报告", theme_id="enterprise", slides=[result])
    payload = render_deck_to_pptx(deck).getvalue()
    assert verify_pptx(payload, deck).passed
    chart = next(b for b in result.blocks if b.type == "chart")
    chart.series[0].values[0] = 999
    assert not verify_pptx(payload, deck).passed
    assert any(shape.has_chart for shape in Presentation(BytesIO(payload)).slides[0].shapes)


def test_deck_missing_summary_and_decision_are_visible():
    slides = [slide().model_copy(update={"id": str(i)}) for i in range(5)]
    plans = {s.id: plan(evidence=[]) for s in slides}
    deck = Deck(id="d", title="报告", theme_id="enterprise", slides=slides)
    codes = {
        i.code
        for i in check_report_quality(
            deck,
            plans,
            {},
            DeckBlueprint(),
            ReportBrief(scenario="business_review", decision_request="确认推广方向"),
        )
    }
    assert {"missing_summary", "missing_decision", "missing_close"} <= codes


def test_preview_fingerprint_changes_with_content_and_theme():
    deck = Deck(id="d", title="报告", theme_id="enterprise", slides=[slide()])
    original = preview_fingerprint(deck, get_theme("enterprise"))
    assert original == preview_fingerprint(deck, get_theme("enterprise"))
    assert original != preview_fingerprint(deck, get_theme("enterprise-dark"))
    deck.slides[0].blocks[0].text = "最新经营复盘"
    assert original != preview_fingerprint(deck, get_theme("enterprise"))


def test_preview_timeout_is_retryable(monkeypatch):
    key = f"previews/test/{uuid.uuid4()}"
    save_preview_status(key, "queued")
    assert load_preview_status(key)["status"] == "queued"
    monkeypatch.setattr("app.services.preview.time.time", lambda: 10**12)
    assert load_preview_status(key)["status"] == "failed"
