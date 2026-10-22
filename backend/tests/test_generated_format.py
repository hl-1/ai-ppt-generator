from __future__ import annotations

import json
import uuid
from pathlib import Path

import pytest

from app.engine.content.content import Slide
from app.engine.content.content_format import has_temporal_sequence, unnumber_heading
from app.engine.content.content_pagination import split_generated_slide
from app.engine.content.outline import OutlinePageDraft
from app.engine.content.slide_draft import FlexSlideDraft
from app.engine.layout.enterprise_layout import compose_report_slide
from app.engine.layout.generated_layout import fit_generated_slide, normalize_generated_diagrams
from app.engine.layout.theme import get_theme, load_themes
from app.engine.quality.validation import validate_slide
from app.infrastructure.llm.base import OutlineSourceSection, SlideGenerationInput
from app.modules.decks.workflow import build_slide_workflow, run_slide_workflow

CASES = json.loads(
    (Path(__file__).parent / "fixtures/generated_format_slides.json").read_text(encoding="utf-8")
)


@pytest.mark.parametrize(
    "heading",
    [
        "01 看清差距",
        "01 01 看清差距",
        "1. 看清差距",
        "（一）看清差距",
        "一、看清差距",
        "第1章 看清差距",
    ],
)
def test_agenda_owns_numbering(heading):
    assert unnumber_heading(heading) == "看清差距"
    assert unnumber_heading("2026年技能规划") == "2026年技能规划"


def test_time_management_is_not_a_timeline():
    assert not has_temporal_sequence(["资源分层建议", "时间安排示例", "利用工作制度"])
    assert has_temporal_sequence(["2026年：试点", "2027年：推广"])
    assert has_temporal_sequence(["准备阶段：明确需求", "实施阶段：完成交付"])


def _texts(blocks):
    result = {}
    for block in blocks:
        if block.type == "cards":
            result.setdefault(block.id, []).extend((item.title, item.desc) for item in block.items)
        elif block.type == "bullets":
            result.setdefault(block.id, []).extend(block.items)
        elif block.type == "text":
            result.setdefault(block.id, []).append(block.text)
    return result


@pytest.mark.parametrize("theme_id", list(load_themes()))
@pytest.mark.parametrize("case", CASES, ids=[case["plan"]["title"] for case in CASES])
def test_real_generated_pages_are_readable_and_lossless_in_every_theme(case, theme_id):
    slide = Slide.model_validate(case["slide"])
    plan = OutlinePageDraft.model_validate(case["plan"])
    slide = normalize_generated_diagrams(slide)
    if plan.page_role == "toc":
        slide = compose_report_slide(slide, plan)
        again = compose_report_slide(slide, plan)
        assert list(_texts(slide.blocks).values()) == list(_texts(again.blocks).values())
    before = _texts(slide.blocks)
    chunks = split_generated_slide(slide, get_theme(theme_id))
    assert all(
        not any(issue.severity == "error" for issue in validate_slide(chunk, theme_id=theme_id))
        for chunk in chunks
    )
    after = _texts([block for chunk in chunks for block in chunk.blocks])
    for block in slide.blocks:
        if block.type in {"cards", "bullets"}:
            assert after[block.id] == before[block.id]
        elif block.type == "text" and not block.id.endswith("-title"):
            assert "".join(after[block.id]) == "".join(before[block.id])
    if plan.page_role == "toc":
        assert len(chunks) == 1
        assert not any(
            issue.code == "duplicate_numbering"
            for chunk in chunks
            for issue in validate_slide(chunk, theme_id=theme_id)
        )


def test_nested_card_fitting_does_not_accumulate_spacers_or_clip():
    slide = Slide.model_validate(CASES[1]["slide"])
    theme = get_theme("enterprise")
    once = fit_generated_slide(slide, theme)
    twice = fit_generated_slide(once, theme)
    assert not [issue for issue in validate_slide(twice, theme=theme) if issue.severity == "error"]
    assert once.layout_tree.model_dump() == twice.layout_tree.model_dump()


def test_pagination_fails_at_page_limit_without_discarding_content():
    slide = Slide.model_validate(CASES[2]["slide"])
    original = slide.model_dump()
    # Force a real continuation rather than a cosmetic template change.
    bullets = next(block for block in slide.blocks if block.type == "bullets")
    bullets.items = bullets.items * 6
    with pytest.raises(ValueError, match="页数上限"):
        split_generated_slide(slide, get_theme("enterprise"), max_parts=1)
    assert (
        len(bullets.items)
        == len(next(b for b in original["blocks"] if b["type"] == "bullets")["items"]) * 6
    )


@pytest.mark.parametrize("topic_mode", [False, True], ids=["document", "topic"])
@pytest.mark.parametrize("case", CASES, ids=[case["plan"]["title"] for case in CASES])
async def test_both_generation_inputs_use_formatting_and_continuations(case, topic_mode):
    draft = FlexSlideDraft.model_validate(
        {
            "blocks": case["slide"]["blocks"],
            "layout_tree": case["slide"]["layout_tree"],
        }
    )

    class Generator:
        async def generate(self, payload):
            return draft

    payload = SlideGenerationInput(
        deck_title="工作中的技能提升",
        tone="professional",
        position=2,
        total_pages=10,
        page_title=case["plan"]["title"],
        topic_mode=topic_mode,
        sections=[
            OutlineSourceSection(
                ref="S1:1", level=1, locator="p1", text="围绕日常任务明确目标、实践并复盘。"
            )
        ],
        layout_mode="flex",
        **{key: value for key, value in case["plan"].items() if key not in {"title"}},
    )
    slide, _ = await run_slide_workflow(
        build_slide_workflow(Generator()), payload, uuid.uuid4(), theme_id="enterprise"
    )
    chunks = split_generated_slide(slide, get_theme("enterprise"))
    assert all(
        not any(issue.severity == "error" for issue in validate_slide(chunk, theme_id="enterprise"))
        for chunk in chunks
    )
