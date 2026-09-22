from app.domain.content import ChartBlock, Slide, TextBlock
from app.domain.enterprise_layout import bind_planned_evidence
from app.domain.evidence import prepare_page_plan
from app.domain.flex_layout import FlexContainer, FlexLeaf
from app.domain.outline import OutlinePageDraft
from app.domain.topic_visuals import normalize_topic_pages
from app.services.topic_material import build_topic_sample_document


def _topic_sources() -> dict[str, str]:
    document = build_topic_sample_document(
        topic="AI时代计算机专业的发展与趋势",
        audience="管理层",
        report_brief=None,
    )
    return {
        f"S1:{index}": section.text
        for index, section in enumerate(document.sections, start=1)
    }


def _page(visual_type: str = "auto") -> OutlinePageDraft:
    return OutlinePageDraft(
        title="主题分析",
        objective="说明本页结论",
        key_points=["结论一", "结论二", "结论三"],
        layout_id="bullets",
        visual_type=visual_type,
    )


def test_topic_auto_visuals_rotate_and_bind_distinct_data() -> None:
    sources = _topic_sources()
    pages = normalize_topic_pages([_page() for _ in range(6)], sources)

    assert [page.visual_type for page in pages] == [
        "line",
        "column",
        "pie",
        "bar",
        "flow",
        "timeline",
    ]
    assert [page.evidence_kind for page in pages] == [
        "trend",
        "comparison",
        "composition",
        "comparison",
        "flow",
        "timeline",
    ]
    assert pages[1].evidence != pages[2].evidence
    prepared = [prepare_page_plan(page, sources, topic_mode=True) for page in pages]
    assert prepared[1].evidence != prepared[3].evidence


def test_topic_selected_pie_is_not_downgraded_or_replaced() -> None:
    sources = _topic_sources()
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
