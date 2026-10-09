"""单页 prompt 契约：密度带与页型必须注入 user prompt。"""

import json

import pytest

from app.domain.layout import get_layout
from app.domain.slide_draft import (
    DiagramContent,
    FlexDiagramContent,
    FlexSlideDraft,
    SlideDraft,
    draft_to_slide,
    flex_draft_to_slide,
)
from app.llm.base import SlideGenerationInput
from app.llm.slide import DeepSeekSlideGenerator


def _generator() -> DeepSeekSlideGenerator:
    # 不调用 LLM；只测 prompt 拼装
    return DeepSeekSlideGenerator.__new__(DeepSeekSlideGenerator)


def test_fixed_user_prompt_includes_density_and_role() -> None:
    gen = _generator()
    payload = SlideGenerationInput(
        deck_title="复盘",
        tone="professional",
        position=2,
        total_pages=5,
        page_title="现状",
        objective="认清瓶颈",
        key_points=["交付慢", "重复建设"],
        layout_id="bullets",
        layout_mode="fixed",
        content_density="detailed",
        page_role="content",
    )
    prompt = gen._user_prompt(payload, get_layout("bullets"))
    assert "detailed" in prompt
    assert "文字量档位" in prompt
    assert "page_role" in prompt
    assert "禁止仅输出" in prompt
    assert "宁可少写" not in prompt


def _flex_payload(**overrides) -> SlideGenerationInput:
    base = {
        "deck_title": "复盘",
        "tone": "professional",
        "position": 2,
        "total_pages": 5,
        "page_title": "现状",
        "objective": "认清瓶颈",
        "key_points": ["交付慢", "重复建设"],
        "layout_id": "bullets",
        "layout_mode": "flex",
        "content_density": "medium",
        "page_role": "content",
    }
    return SlideGenerationInput(**(base | overrides))


def test_flex_user_prompt_includes_multi_block_guidance() -> None:
    gen = _generator()
    payload = _flex_payload()
    prompt = gen._flex_user_prompt(payload)
    assert "medium" in prompt
    assert "内容块数量目标" in prompt
    system = gen._flex_system_prompt(payload)
    assert "宁可少写" not in system
    assert "按证据形态组织标题与主体" in system


def test_visual_hint_becomes_a_hard_constraint() -> None:
    """配图意图不能只放在 user prompt 的参数里：那模型可以当没看见。"""
    gen = _generator()
    hint = "团队围着白板讨论路线图"
    system = gen._flex_system_prompt(_flex_payload(visual_hint=hint))
    assert "image 块" in system
    assert hint in system
    assert hint in gen._flex_user_prompt(_flex_payload(visual_hint=hint))

    assert "image 块" not in gen._flex_system_prompt(_flex_payload())


def test_skeleton_hint_becomes_a_hard_constraint() -> None:
    gen = _generator()
    system = gen._flex_system_prompt(_flex_payload(skeleton_hint="左文右卡：左栏标题，右栏卡片"))
    assert "左文右卡" in system


def test_callout_quota_is_stated_either_way() -> None:
    gen = _generator()
    assert "最多使用一个 variant=note" in gen._flex_system_prompt(_flex_payload())
    system = gen._flex_system_prompt(_flex_payload(allow_callout=False))
    assert "不得出现 callout 强调框" in system
    assert "不得出现来源说明块" in system


@pytest.mark.parametrize("layout_mode", ["fixed", "flex"])
def test_diagram_prompt_uses_structured_nodes_without_mermaid(layout_mode: str) -> None:
    gen = _generator()
    system = (
        gen._system_prompt(get_layout("chart"))
        if layout_mode == "fixed"
        else gen._flex_system_prompt(_flex_payload(visual_type="flow"))
    )
    example = next(line for line in system.splitlines() if line.startswith("- diagram: "))
    diagram = json.loads(example.removeprefix("- diagram: "))

    assert "mermaid" not in diagram
    assert "禁止输出 mermaid" in system
    nodes = {node["id"] for node in diagram["nodes"]}
    assert all(edge["source"] in nodes and edge["target"] in nodes for edge in diagram["edges"])


@pytest.mark.parametrize("layout_mode", ["fixed", "flex"])
def test_diagram_without_mermaid_renders_server_generated_source(layout_mode: str) -> None:
    import uuid

    nodes = [
        {"id": "start", "title": "核验"},
        {"id": "yes", "title": "通过"},
        {"id": "no", "title": "退回"},
    ]
    edges = [
        {"source": "start", "target": "yes", "label": "充分"},
        {"source": "start", "target": "no", "label": "不足"},
    ]
    if layout_mode == "fixed":
        draft = SlideDraft(
            blocks=[DiagramContent(slot_id="visual", diagram_type="flow", nodes=nodes, edges=edges)]
        )
        slide = draft_to_slide(uuid.uuid4(), "chart", draft)
    else:
        draft = FlexSlideDraft(
            blocks=[
                FlexDiagramContent(id="diagram", diagram_type="flow", nodes=nodes, edges=edges)
            ],
            layout_tree={
                "type": "column",
                "id": "root",
                "children": [{"type": "block", "id": "leaf", "block_id": "diagram"}],
            },
        )
        slide = flex_draft_to_slide(uuid.uuid4(), draft)

    diagram = slide.blocks[0]
    assert diagram.type == "diagram"
    assert diagram.mermaid.startswith("flowchart TB")
    assert "核验" in diagram.mermaid
    assert len(diagram.edges) == 2
