import uuid

import pytest

from app.domain.slide_draft import BulletsContent, SlideDraft, TextContent
from app.llm.base import OutlineSourceSection, SlideGenerationInput
from app.workflows.slide import (
    build_slide_workflow,
    prepare_slide_input,
    run_slide_workflow,
)


def _payload(**overrides) -> SlideGenerationInput:
    base = {
        "deck_title": "平台化复盘",
        "tone": "professional",
        "position": 2,
        "total_pages": 5,
        "page_title": "现状与问题",
        "objective": "让听众认清当前瓶颈",
        "key_points": ["交付慢", "重复建设"],
        "layout_id": "bullets",
    }
    return SlideGenerationInput(**{**base, **overrides})


class ScriptedGenerator:
    def __init__(self, drafts: list[SlideDraft]) -> None:
        self._drafts = drafts
        self.prompts: list[list[str]] = []

    async def generate(self, payload: SlideGenerationInput) -> SlideDraft:
        self.prompts.append(list(payload.issues))
        return self._drafts[min(len(self.prompts) - 1, len(self._drafts) - 1)]


def _draft(items: list[str]) -> SlideDraft:
    return SlideDraft(
        blocks=[
            TextContent(slot_id="title", text="现状与问题"),
            BulletsContent(slot_id="body", items=items),
        ]
    )


def test_prepare_trims_sections_within_budget() -> None:
    payload = _payload(
        sections=[
            OutlineSourceSection(ref="S1:1", level=1, text="内容" * 5_000, locator="p1"),
            OutlineSourceSection(ref="S1:2", level=1, text="补充" * 5_000, locator="p2"),
        ]
    )

    prepared = prepare_slide_input(payload)

    total = sum(len(section.text) for section in prepared.sections)
    assert total <= 6_000
    assert [section.ref for section in prepared.sections] == ["S1:1", "S1:2"]


@pytest.mark.asyncio
async def test_workflow_repairs_capacity_overflow_once() -> None:
    too_long = ["超出容量的要点" * 12] * 9
    generator = ScriptedGenerator([_draft(too_long), _draft(["精简要点一", "精简要点二"])])
    workflow = build_slide_workflow(generator)

    slide, issues = await run_slide_workflow(workflow, _payload(), uuid.uuid4())

    # 第二轮带上了结构问题，说明修复是定向的而不是无脑重试
    assert generator.prompts[0] == []
    assert generator.prompts[1]
    assert issues == []
    assert slide.blocks[1].items == ["精简要点一", "精简要点二"]


@pytest.mark.asyncio
async def test_workflow_gives_up_after_one_repair() -> None:
    too_long = ["超出容量的要点" * 12] * 9
    generator = ScriptedGenerator([_draft(too_long)])
    workflow = build_slide_workflow(generator)

    _, issues = await run_slide_workflow(workflow, _payload(), uuid.uuid4())

    assert len(generator.prompts) == 2
    assert issues
