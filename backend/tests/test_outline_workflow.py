from __future__ import annotations

import json
from typing import Any

import pytest

from app.core.config import Settings
from app.domain.outline import OutlineDraft, OutlinePage, OutlinePageDraft
from app.llm.base import OutlineGenerationInput, OutlineSourceSection
from app.llm.client import create_chat_model
from app.llm.deepseek import (
    DeepSeekOutlineGenerator,
    InvalidOutlineOutputError,
    LLMNotConfiguredError,
)
from app.workflows.outline import (
    MAX_SECTION_CHARS,
    MAX_TOTAL_SOURCE_CHARS,
    build_outline_workflow,
    prepare_outline_input,
    run_outline_workflow,
)


def _section(
    ref: str,
    text: str,
    *,
    heading: str | None = None,
    level: int = 1,
    locator: str = "p1",
) -> OutlineSourceSection:
    return OutlineSourceSection(
        ref=ref,
        heading=heading,
        level=level,
        text=text,
        locator=locator,
    )


def _input(
    *,
    page_count: int = 3,
    sections: list[OutlineSourceSection] | None = None,
) -> OutlineGenerationInput:
    return OutlineGenerationInput(
        title="季度业务复盘",
        audience="管理层",
        tone="professional",
        page_count=page_count,
        sections=sections
        or [
            _section("S1:1", "市场增长稳健", heading="市场", level=1),
            _section("S1:2", "成本控制见效", heading="成本", level=2),
        ],
    )


def _draft_pages(count: int, *, layout_id: str = "bullets", refs: list[str] | None = None):
    pages = []
    for index in range(count):
        pages.append(
            OutlinePageDraft(
                title=f"第 {index + 1} 页",
                objective="说明本页目标",
                key_points=["要点甲", "要点乙"],
                source_refs=refs or [],
                layout_id=layout_id,
            )
        )
    return pages


class FakeOutlineGenerator:
    def __init__(self, pages: list[OutlinePageDraft] | None = None) -> None:
        self.calls: list[OutlineGenerationInput] = []
        self._pages = pages

    async def generate(self, payload: OutlineGenerationInput) -> OutlineDraft:
        self.calls.append(payload)
        pages = self._pages or _draft_pages(payload.page_count, refs=["S1:1"])
        return OutlineDraft(pages=pages)


class FakeChat:
    def __init__(self, payload: str, api_key: str = "test-key") -> None:
        self.payload = payload
        self._api_key = api_key
        self.last_system: str | None = None
        self.last_user: str | None = None
        self.called = False

    async def complete(self, schema: Any, *, system: str, user: str, purpose: str) -> Any:
        if not self._api_key.strip():
            raise LLMNotConfiguredError(f"未配置 LLM API Key，无法{purpose}")
        self.called = True
        self.last_system = system
        self.last_user = user
        return schema.model_validate_json(self.payload)


class SequenceChat:
    def __init__(self, payloads: list[str]) -> None:
        self.payloads = payloads
        self.system_prompts: list[str] = []

    async def complete(self, schema: Any, *, system: str, user: str, purpose: str) -> Any:
        self.system_prompts.append(system)
        payload = self.payloads[min(len(self.system_prompts) - 1, len(self.payloads) - 1)]
        return schema.model_validate_json(payload)


def test_prepare_trims_long_section_without_breaking_ref() -> None:
    long_text = "甲" * (MAX_SECTION_CHARS + 500)
    payload = _input(sections=[_section("S1:1", long_text, heading="长节", level=2)])

    prepared = prepare_outline_input(payload)

    assert len(prepared.sections) == 1
    section = prepared.sections[0]
    assert section.ref == "S1:1"
    assert section.heading == "长节"
    assert section.level == 2
    assert len(section.text) == MAX_SECTION_CHARS


def test_prepare_respects_total_budget_and_keeps_earlier_refs() -> None:
    sections = [
        _section("S1:1", "A" * 100, heading="一"),
        _section("S1:2", "B" * 100, heading="二"),
        _section("S1:3", "C" * 100, heading="三"),
    ]
    payload = _input(sections=sections)

    prepared = prepare_outline_input(payload, max_total_chars=180, max_section_chars=100)

    assert [item.ref for item in prepared.sections] == ["S1:1", "S1:2"]
    total = sum(len(item.text) + len(item.heading or "") for item in prepared.sections)
    assert total <= 180
    # 第二节可能被部分截断，但 ref 仍完整对应同一节
    assert prepared.sections[1].ref == "S1:2"
    assert prepared.sections[1].text.startswith("B")


def test_prepare_skips_empty_sections() -> None:
    payload = _input(
        sections=[
            _section("S1:1", "  \n\t  ", heading=None),
            _section("S1:2", "有效内容", heading="保留"),
        ]
    )
    prepared = prepare_outline_input(payload)
    assert [item.ref for item in prepared.sections] == ["S1:2"]


@pytest.mark.asyncio
async def test_workflow_prepare_and_page_count_flow() -> None:
    generator = FakeOutlineGenerator()
    workflow = build_outline_workflow(generator)
    payload = _input(
        page_count=4,
        sections=[
            _section("S2:1", "产品进展", heading="产品", level=1, locator="第 2 页"),
            _section("S2:2", "风险清单", heading="风险", level=2, locator="第 5 页"),
        ],
    )

    draft = await run_outline_workflow(workflow, payload)

    assert len(draft.pages) == 4
    assert len(generator.calls) == 1
    prepared = generator.calls[0]
    assert prepared.page_count == 4
    assert prepared.title == payload.title
    assert [item.ref for item in prepared.sections] == ["S2:1", "S2:2"]
    assert prepared.sections[0].locator == "第 2 页"


@pytest.mark.asyncio
async def test_workflow_trims_long_input_before_generate() -> None:
    generator = FakeOutlineGenerator()
    workflow = build_outline_workflow(generator)
    oversized = [_section(f"S1:{index}", "X" * 3_000, heading=f"H{index}") for index in range(1, 8)]
    payload = _input(page_count=5, sections=oversized)

    await run_outline_workflow(workflow, payload)

    prepared = generator.calls[0]
    total = sum(len(item.text) + len(item.heading or "") for item in prepared.sections)
    assert total <= MAX_TOTAL_SOURCE_CHARS
    assert all(len(item.text) <= MAX_SECTION_CHARS for item in prepared.sections)
    assert prepared.sections[0].ref == "S1:1"


def _valid_outline_json(
    page_count: int = 2,
    *,
    layout_id: str = "bullets",
    ref: str = "S1:1",
) -> str:
    draft = OutlineDraft(pages=_draft_pages(page_count, layout_id=layout_id, refs=[ref]))
    return draft.model_dump_json()


def _valid_outline_page_json() -> str:
    response = json.loads(_valid_outline_json(page_count=1))
    response["pages"][0]["title"] = "补充说明"
    response["pages"][0]["layout_id"] = "unknown-layout"
    response["pages"][0]["source_refs"] = ["S9:9"]
    return json.dumps(response["pages"][0], ensure_ascii=False)


@pytest.mark.asyncio
async def test_deepseek_parses_valid_outline() -> None:
    chat = FakeChat(_valid_outline_json())
    generator = DeepSeekOutlineGenerator(
        chat=chat,
        layout_ids=frozenset({"bullets", "cover"}),
    )

    draft = await generator.generate(_input(page_count=2))
    assert len(draft.pages) == 2
    assert chat.called


@pytest.mark.asyncio
async def test_deepseek_normalizes_evidence_kinds_mistaken_for_narrative_roles() -> None:
    response = json.loads(_valid_outline_json(page_count=2))
    response["pages"][0]["narrative_role"] = "composition"
    response["pages"][0]["evidence_kind"] = "composition"
    response["pages"][1]["narrative_role"] = "comparison"
    response["pages"][1]["evidence_kind"] = "comparison"
    chat = FakeChat(json.dumps(response, ensure_ascii=False))
    generator = DeepSeekOutlineGenerator(
        chat=chat,
        layout_ids=frozenset({"bullets"}),
    )

    draft = await generator.generate(_input(page_count=2))

    assert [page.narrative_role for page in draft.pages] == ["performance", "performance"]
    assert "严禁把 trend、comparison、composition" in (chat.last_system or "")


@pytest.mark.asyncio
async def test_deepseek_retries_once_when_model_returns_wrong_page_count() -> None:
    chat = SequenceChat([_valid_outline_json(page_count=1), _valid_outline_page_json()])
    generator = DeepSeekOutlineGenerator(
        chat=chat,
        layout_ids=frozenset({"bullets"}),
    )

    draft = await generator.generate(_input(page_count=2))

    assert len(draft.pages) == 2
    assert len(chat.system_prompts) == 2
    assert draft.pages[-1].title == "补充说明"
    assert draft.pages[-1].layout_id == "bullets"
    assert draft.pages[-1].source_refs == []


def test_create_chat_model_disables_thinking_by_default() -> None:
    model = create_chat_model(Settings(llm_api_key="k", llm_thinking_enabled=False))
    assert model.extra_body == {"thinking": {"type": "disabled"}}


def test_create_chat_model_enables_thinking() -> None:
    model = create_chat_model(Settings(llm_api_key="k", llm_thinking_enabled=True))
    assert model.extra_body == {"thinking": {"type": "enabled"}}


@pytest.mark.asyncio
async def test_deepseek_falls_back_from_illegal_layout_without_regenerating() -> None:
    chat = SequenceChat([_valid_outline_json(layout_id="not-a-layout")])
    generator = DeepSeekOutlineGenerator(
        chat=chat,
        layout_ids=frozenset({"bullets", "cover"}),
    )

    draft = await generator.generate(_input(page_count=2))

    assert len(chat.system_prompts) == 1
    assert [page.layout_id for page in draft.pages] == ["bullets", "bullets"]
    assert [page.model_dump(exclude={"layout_id"}) for page in draft.pages] == [
        page.model_dump(exclude={"layout_id"}) for page in _draft_pages(2, refs=["S1:1"])
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("layout_id", ["two_column", "TwoColumn", "TWO-COLUMN", " two columns "])
async def test_deepseek_normalizes_layout_names(layout_id: str) -> None:
    generator = DeepSeekOutlineGenerator(
        chat=FakeChat(_valid_outline_json(layout_id=layout_id)),
        layout_ids=frozenset({"bullets", "two-column"}),
    )

    draft = await generator.generate(_input(page_count=2))

    assert [page.layout_id for page in draft.pages] == ["two-column", "two-column"]


@pytest.mark.asyncio
@pytest.mark.parametrize("page_role", ["cover", "toc", "section", "summary"])
async def test_deepseek_layout_fallback_respects_page_role(page_role: str) -> None:
    response = json.loads(_valid_outline_json(page_count=1, layout_id="unknown"))
    response["pages"][0]["page_role"] = page_role
    generator = DeepSeekOutlineGenerator(
        chat=FakeChat(json.dumps(response)),
        layout_ids=frozenset({"bullets", page_role}),
    )

    draft = await generator.generate(_input(page_count=1))

    assert draft.pages[0].layout_id == page_role


@pytest.mark.asyncio
@pytest.mark.parametrize("layout_id", ["two_column", None])
async def test_deepseek_fallback_only_uses_installed_layouts(layout_id: str | None) -> None:
    response = json.loads(_valid_outline_json(page_count=1))
    response["pages"][0]["layout_id"] = layout_id
    generator = DeepSeekOutlineGenerator(
        chat=FakeChat(json.dumps(response)),
        layout_ids=frozenset({"bullets"}),
    )

    draft = await generator.generate(_input(page_count=1))

    assert draft.pages[0].layout_id == "bullets"


@pytest.mark.asyncio
async def test_deepseek_normalizes_model_field_types_and_names() -> None:
    response = {
        "blueprint": {"coreMessage": None, "narrative": "Overview\nConclusion"},
        "pages": [
            {
                "title": "Revenue",
                "objective": "Review growth",
                "keyPoints": "Revenue grew\nGrowth continued",
                "sourceRefs": "S1:1",
                "layoutId": "two_column",
                "pageRole": "BODY",
                "narrativeRole": "executive-summary",
                "evidenceKind": "TREND",
                "visualType": "line_chart",
                "keyMessage": None,
                "planningNotes": None,
                "evidence": [
                    {
                        "sourceRef": "S1:1",
                        "quote": "2024 revenue: 100",
                        "value": 100,
                        "period": 2024,
                        "metric": None,
                    }
                ],
            }
        ],
    }
    generator = DeepSeekOutlineGenerator(
        chat=FakeChat(json.dumps(response)),
        layout_ids=frozenset({"bullets", "two-column"}),
    )

    draft = await generator.generate(_input(page_count=1))

    assert draft.blueprint.core_message == ""
    assert draft.blueprint.narrative == ["Overview", "Conclusion"]
    page = draft.pages[0]
    assert page.key_points == ["Revenue grew", "Growth continued"]
    assert page.source_refs == ["S1:1"]
    assert page.page_role == "content"
    assert page.narrative_role == "executive_summary"
    assert page.evidence_kind == "trend"
    assert page.visual_type == "line"
    assert page.key_message == ""
    assert page.planning_notes == []
    assert page.evidence[0].value == "100"
    assert page.evidence[0].period == "2024"
    assert page.evidence[0].quote == "2024 revenue: 100"


@pytest.mark.asyncio
async def test_deepseek_accepts_pages_array_and_optional_nulls() -> None:
    pages = json.loads(_valid_outline_json(page_count=1))["pages"]
    pages[0].update(source_refs=None, evidence=None, visual_type=None)
    pages[0].pop("layout_id")
    generator = DeepSeekOutlineGenerator(
        chat=FakeChat(json.dumps(pages)),
        layout_ids=frozenset({"bullets"}),
    )

    draft = await generator.generate(_input(page_count=1))

    assert draft.pages[0].source_refs == []
    assert draft.pages[0].evidence == []
    assert draft.pages[0].visual_type == "auto"
    assert draft.pages[0].layout_id == "bullets"


@pytest.mark.asyncio
async def test_deepseek_repair_receives_specific_field_errors() -> None:
    response = json.loads(_valid_outline_json(page_count=1))
    response["pages"][0].pop("objective")
    chat = SequenceChat([json.dumps(response), _valid_outline_json(page_count=1)])
    generator = DeepSeekOutlineGenerator(chat=chat, layout_ids=frozenset({"bullets"}))

    draft = await generator.generate(_input(page_count=1))

    assert len(draft.pages) == 1
    assert len(chat.system_prompts) == 2
    assert "pages.0.objective: missing" in chat.system_prompts[1]


@pytest.mark.asyncio
async def test_deepseek_repair_receives_invalid_reference() -> None:
    chat = SequenceChat(
        [
            _valid_outline_json(page_count=1, ref="S9:9"),
            _valid_outline_json(page_count=1),
        ]
    )
    generator = DeepSeekOutlineGenerator(chat=chat, layout_ids=frozenset({"bullets"}))

    draft = await generator.generate(_input(page_count=1))

    assert draft.pages[0].source_refs == ["S1:1"]
    assert len(chat.system_prompts) == 2
    assert "S9:9" in chat.system_prompts[1]


@pytest.mark.asyncio
async def test_deepseek_does_not_invent_missing_content() -> None:
    response = json.loads(_valid_outline_json(page_count=1))
    response["pages"][0]["key_points"] = []
    generator = DeepSeekOutlineGenerator(
        chat=FakeChat(json.dumps(response)),
        layout_ids=frozenset({"bullets"}),
    )

    with pytest.raises(InvalidOutlineOutputError):
        await generator.generate(_input(page_count=1))


@pytest.mark.asyncio
async def test_deepseek_refit_uses_same_normalization_and_preserves_page_role() -> None:
    response = {
        "title": "Revenue trend",
        "objective": "Explain growth",
        "keyPoints": "Revenue grew\nGrowth continued",
        "sourceRefs": "S1:1",
        "layoutId": "line_chart",
        "pageRole": "BODY",
        "narrativeRole": "supporting",
        "evidenceKind": "TREND",
        "visualType": "line_chart",
        "evidence": [{"sourceRef": "S1:1", "quote": "Revenue: 100", "value": 100}],
    }
    generator = DeepSeekOutlineGenerator(
        chat=FakeChat(json.dumps(response)),
        layout_ids=frozenset({"bullets", "chart"}),
    )
    page = OutlinePageDraft(
        title="Revenue",
        objective="Explain growth",
        key_points=["Growth", "Next steps"],
        layout_id="bullets",
        page_role="summary",
        narrative_role="summary",
    )

    fitted = await generator.refit_page(page, "trend", [_section("S1:1", "Revenue: 100")])

    assert fitted.page_role == "summary"
    assert fitted.narrative_role == "summary"
    assert fitted.layout_id == "chart"
    assert fitted.evidence_kind == "trend"
    assert fitted.evidence[0].value == "100"
    assert fitted.evidence[0].source_ref == "S1:1"


@pytest.mark.asyncio
async def test_deepseek_rejects_illegal_ref() -> None:
    generator = DeepSeekOutlineGenerator(
        chat=FakeChat(_valid_outline_json(ref="S9:9")),
        layout_ids=frozenset({"bullets"}),
    )

    with pytest.raises(InvalidOutlineOutputError, match="未知来源引用"):
        await generator.generate(_input(page_count=2))


@pytest.mark.asyncio
async def test_deepseek_missing_api_key() -> None:
    chat = FakeChat(_valid_outline_json(), api_key="   ")
    generator = DeepSeekOutlineGenerator(chat=chat, layout_ids=frozenset({"bullets"}))

    with pytest.raises(LLMNotConfiguredError, match="未配置 LLM API Key"):
        await generator.generate(_input(page_count=2))

    assert chat.called is False


def test_system_prompt_only_names_existing_layouts() -> None:
    """提示词里出现过的 layout_id 都必须能通过校验，否则等于诱导模型踩坑。"""
    layout_ids = frozenset({"bullets", "cover", "two-column"})
    generator = DeepSeekOutlineGenerator(
        chat=FakeChat(_valid_outline_json()),
        layout_ids=layout_ids,
    )

    prompt = generator._system_prompt()

    assert "two-column" in prompt
    for absent in ("image-text", "kpi", "chart", "table", "image-left"):
        assert f"layout_id={absent}" not in prompt
        assert f"layout_id 为 {absent}" not in prompt


def test_system_prompt_without_multi_slot_layouts() -> None:
    generator = DeepSeekOutlineGenerator(
        chat=FakeChat(_valid_outline_json()),
        layout_ids=frozenset({"bullets", "cover"}),
    )

    assert "多槽布局" not in generator._system_prompt()


def test_real_layouts_cover_the_preferred_multi_slot_hints() -> None:
    """提示里的推荐布局全部落空时只剩一句空话，等于悄悄退化。"""
    generator = DeepSeekOutlineGenerator(chat=FakeChat(_valid_outline_json()))

    assert "多槽布局" in generator._system_prompt()


def test_refit_user_prompt_serializes_outline_page_uuid() -> None:
    """重构页面提示词必须能序列化真实 OutlinePage 的 UUID。"""
    generator = DeepSeekOutlineGenerator(
        chat=FakeChat(_valid_outline_json()),
        layout_ids=frozenset({"bullets", "chart"}),
    )
    page = OutlinePage(
        title="收入趋势",
        objective="展示收入变化",
        key_points=["收入上升", "增长持续"],
        layout_id="bullets",
    )

    prompt = generator._refit_user_prompt(
        page,
        "trend",
        [_section("S1:1", "2023 年收入 100 万元。")],
    )

    body = json.loads(prompt.split("\n", 1)[1])
    assert body["current_page"]["id"] == str(page.id)
