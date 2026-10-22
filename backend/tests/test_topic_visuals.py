import pytest

from app.engine.content.content import ChartBlock, Slide, TextBlock
from app.engine.content.evidence import prepare_page_plan
from app.engine.content.outline import OutlinePageDraft
from app.engine.layout.enterprise_layout import bind_planned_evidence
from app.engine.layout.flex_layout import FlexContainer, FlexLeaf
from app.engine.layout.topic_visuals import normalize_topic_pages
from app.modules.outlines.topic_material import build_topic_document


def _topic_sources() -> dict[str, str]:
    document = build_topic_document(topic="春节去北京旅游规划")
    return {f"S1:{index}": section.text for index, section in enumerate(document.sections, start=1)}


def _page(visual_type: str = "auto") -> OutlinePageDraft:
    return OutlinePageDraft(
        title="主题分析",
        objective="说明本页结论",
        key_points=["结论一", "结论二", "结论三"],
        layout_id="bullets",
        visual_type=visual_type,
    )


def test_topic_auto_visuals_do_not_inject_unrelated_sample_charts() -> None:
    sources = _topic_sources()
    pages = normalize_topic_pages([_page() for _ in range(6)], sources)

    assert all(page.visual_type == "auto" for page in pages)
    assert all(page.evidence == [] for page in pages)
    prepared = [prepare_page_plan(page, sources, topic_mode=True) for page in pages]
    assert all(page.evidence == [] for page in prepared)


def test_topic_selected_pie_is_not_downgraded_or_replaced() -> None:
    sources = {
        "S1:1": "\n".join(
            f"指标：用户预算；分类：{category}；数值：{value}%；单位：%；时间：计划期间；范围：北京旅行。"
            for category, value in (("住宿", 60), ("交通", 40))
        )
    }
    plan = prepare_page_plan(_page("pie"), sources, topic_mode=True)
    slide = Slide(
        id="topic-slide",
        layout_id="bullets",
        layout_mode="flex",
        blocks=[TextBlock(id="title", slot_id="title", text="主题分析")],
        layout_tree=FlexContainer(
            type="column",
            id="root",
            children=[FlexLeaf(id="title-leaf", block_id="title", text_style="title")],
        ),
    )

    result = bind_planned_evidence(slide, plan, topic_mode=True)

    assert plan.evidence_kind == "composition"
    chart = next(block for block in result.blocks if isinstance(block, ChartBlock))
    assert chart.chart_type == "pie"


@pytest.mark.parametrize("visual_type", ["line", "column", "bar", "pie", "combo_chart"])
def test_topic_numeric_visual_without_evidence_becomes_qualitative(visual_type: str) -> None:
    page = _page(visual_type).model_copy(
        update={
            "layout_id": "chart",
            "evidence_kind": "trend" if visual_type == "line" else "comparison",
        }
    )

    plan = prepare_page_plan(page, _topic_sources(), topic_mode=True)

    assert plan.evidence_kind == "narrative"
    assert plan.visual_type == "auto"
    assert plan.layout_id == "bullets"
    assert plan.evidence == []
    assert plan.planning_notes


def test_travel_advice_with_time_words_does_not_become_a_timeline() -> None:
    page = _page().model_copy(
        update={
            "title": "交通出行全攻略",
            "objective": "春节北京旅行交通规划",
            "key_points": ["景区游览路线优先按地铁分组", "进站安检需预留时间"],
        }
    )

    plan = prepare_page_plan(page, _topic_sources(), topic_mode=True)

    assert plan.visual_type == "auto"
    assert plan.evidence_kind == "narrative"


@pytest.mark.parametrize("explicit", [False, True])
def test_timeline_requires_sequence_unless_explicitly_selected(explicit: bool) -> None:
    page = _page("timeline" if explicit else "auto").model_copy(
        update={
            "title": "资源与时间安排",
            "evidence_kind": "timeline",
            "key_points": ["资源分层建议", "筛选原则", "时间安排示例", "利用工作制度"],
        }
    )
    result = normalize_topic_pages([page], {})[0]
    assert result.visual_type == ("timeline" if explicit else "auto")
    assert result.evidence_kind == ("timeline" if explicit else "narrative")


def test_timeline_with_actual_phases_is_suggested() -> None:
    page = _page().model_copy(update={"key_points": ["第一阶段：启动", "第二阶段：试点"]})
    assert normalize_topic_pages([page], {})[0].visual_type == "timeline"
