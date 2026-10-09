import asyncio
import json
import uuid

import pytest

from app.domain.slide_draft import BulletsContent, SlideDraft, TextContent
from app.llm.base import OutlineSourceSection, SlideGenerationInput
from app.llm.errors import (
    InvalidSlideOutputError,
    LLMNotConfiguredError,
    LLMTimeoutError,
    LLMUnavailableError,
    safe_error_details,
)
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
        "layout_mode": "fixed",
        "content_density": "medium",
        "page_role": "content",
    }
    return SlideGenerationInput(**{**base, **overrides})


class ScriptedGenerator:
    def __init__(self, drafts: list[SlideDraft | BaseException]) -> None:
        self._drafts = drafts
        self.prompts: list[list[str]] = []

    async def generate(self, payload: SlideGenerationInput) -> SlideDraft:
        self.prompts.append(list(payload.issues))
        draft = self._drafts[min(len(self.prompts) - 1, len(self._drafts) - 1)]
        if isinstance(draft, BaseException):
            raise draft
        return draft


def _draft(items: list[str], *, title: str = "现状与问题") -> SlideDraft:
    return SlideDraft(
        blocks=[
            TextContent(slot_id="title", text=title),
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
async def test_workflow_skips_repair_for_capacity_overflow() -> None:
    """容量/溢出 warning 只提示，不触发整页重写。"""
    too_long = ["超出容量的要点" * 12] * 9
    generator = ScriptedGenerator([_draft(too_long)])
    workflow = build_slide_workflow(generator)

    slide, issues = await run_slide_workflow(workflow, _payload(), uuid.uuid4())

    assert len(generator.prompts) == 1
    assert generator.prompts[0] == []
    assert any(issue.code == "capacity" for issue in issues)
    assert slide.blocks[1].items == too_long


@pytest.mark.asyncio
async def test_fixed_workflow_preserves_confirmed_title() -> None:
    generator = ScriptedGenerator(
        [_draft(["具体经营结果与数据", "下一步行动与影响"], title="模型改写标题")]
    )
    slide, _ = await run_slide_workflow(build_slide_workflow(generator), _payload(), uuid.uuid4())

    assert next(block for block in slide.blocks if block.slot_id == "title").text == "现状与问题"


@pytest.mark.asyncio
async def test_topic_workflow_repairs_capacity_overflow_once() -> None:
    too_long = ["主题页过长的要点" * 12] * 9
    generator = ScriptedGenerator(
        [
            _draft(too_long),
            _draft(
                [
                    "交付周期从六周缩短到三周",
                    "重复建设集中在跨团队接口",
                    "下一步统一数据契约与评审节奏",
                ]
            ),
        ]
    )
    workflow = build_slide_workflow(generator)

    slide, issues = await run_slide_workflow(
        workflow,
        _payload(topic_mode=True),
        uuid.uuid4(),
    )

    assert len(generator.prompts) == 2
    assert any("超出" in message or "溢出" in message for message in generator.prompts[1])
    assert slide.blocks[1].items[0] != too_long[0]
    assert not any(issue.code == "capacity" for issue in issues)


@pytest.mark.asyncio
async def test_workflow_repairs_thin_content_once() -> None:
    thin = ["短", "也短"]
    rich = [
        "交付周期从六周缩短到三周，瓶颈在评审排队",
        "重复建设占比过高，跨团队接口缺少统一契约",
        "线上故障平均恢复时间仍超过四小时，需专人值班",
    ]
    generator = ScriptedGenerator([_draft(thin), _draft(rich)])
    workflow = build_slide_workflow(generator)

    slide, issues = await run_slide_workflow(workflow, _payload(), uuid.uuid4())

    assert generator.prompts[0] == []
    assert generator.prompts[1]
    assert any("偏" in msg or "过短" in msg or "空话" in msg for msg in generator.prompts[1])
    assert slide.blocks[1].items == rich
    assert not any(issue.code == "thin_content" for issue in issues)


@pytest.mark.asyncio
async def test_workflow_gives_up_after_one_thin_repair() -> None:
    thin = ["短", "也短"]
    generator = ScriptedGenerator([_draft(thin)])
    workflow = build_slide_workflow(generator)

    _, issues = await run_slide_workflow(workflow, _payload(), uuid.uuid4())

    assert len(generator.prompts) == 2
    assert any(issue.code == "thin_content" for issue in issues)


@pytest.fixture
def immediate_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.workflows.slide.GENERATION_RETRY_DELAY_SECONDS", 0)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error",
    [
        LLMTimeoutError("timeout"),
        LLMUnavailableError("unavailable"),
        InvalidSlideOutputError("json"),
    ],
)
async def test_workflow_retries_model_failures(error: Exception, immediate_retry) -> None:
    rich = ["交付周期从六周缩短到三周，瓶颈在评审排队"] * 3
    generator = ScriptedGenerator([error, _draft(rich)])

    slide, _ = await run_slide_workflow(build_slide_workflow(generator), _payload(), uuid.uuid4())

    assert len(generator.prompts) == 2
    assert slide.blocks[1].items == rich
    if isinstance(error, InvalidSlideOutputError):
        assert "JSON" in generator.prompts[1][-1]
        assert "不输出 mermaid" in generator.prompts[1][-1]


@pytest.mark.asyncio
async def test_workflow_stops_retrying_and_logs_without_materials(immediate_retry, caplog) -> None:
    generator = ScriptedGenerator([LLMTimeoutError("private-provider-response")])
    slide_id = uuid.uuid4()

    with pytest.raises(LLMTimeoutError):
        await run_slide_workflow(build_slide_workflow(generator), _payload(), slide_id)

    assert len(generator.prompts) == 2
    assert str(slide_id) in caplog.text
    assert "attempt=2/2" in caplog.text
    assert "timeout" in caplog.text
    assert "private-provider-response" not in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize("error", [LLMNotConfiguredError("missing key"), RuntimeError("bug")])
async def test_workflow_does_not_retry_configuration_or_internal_errors(error, immediate_retry):
    generator = ScriptedGenerator([error])

    with pytest.raises(type(error)):
        await run_slide_workflow(build_slide_workflow(generator), _payload(), uuid.uuid4())

    assert len(generator.prompts) == 1


@pytest.mark.asyncio
async def test_workflow_keeps_usable_content_when_repair_request_fails(immediate_retry) -> None:
    generator = ScriptedGenerator([_draft(["短", "也短"]), LLMTimeoutError("timeout")])

    slide, issues = await run_slide_workflow(
        build_slide_workflow(generator), _payload(), uuid.uuid4()
    )

    assert len(generator.prompts) == 3
    assert slide.blocks[1].items == ["短", "也短"]
    assert any(issue.code == "repair_failed" for issue in issues)
    assert not any(issue.severity == "error" for issue in issues)


@pytest.mark.asyncio
async def test_workflow_does_not_keep_structurally_invalid_content(immediate_retry) -> None:
    missing_body = SlideDraft(blocks=[TextContent(slot_id="title", text="现状与问题")])
    generator = ScriptedGenerator([missing_body, LLMTimeoutError("timeout")])

    with pytest.raises(LLMTimeoutError):
        await run_slide_workflow(build_slide_workflow(generator), _payload(), uuid.uuid4())

    assert len(generator.prompts) == 3


@pytest.mark.asyncio
async def test_workflow_rejects_structural_regression_during_repair(immediate_retry) -> None:
    missing_body = SlideDraft(blocks=[TextContent(slot_id="title", text="现状与问题")])
    generator = ScriptedGenerator([_draft(["短", "也短"]), missing_body])

    slide, issues = await run_slide_workflow(
        build_slide_workflow(generator), _payload(), uuid.uuid4()
    )

    assert len(generator.prompts) == 2
    assert slide.blocks[1].items == ["短", "也短"]
    assert any(issue.code == "repair_failed" for issue in issues)


@pytest.mark.asyncio
async def test_workflow_keeps_content_when_repair_conversion_raises(monkeypatch) -> None:
    from app.workflows import slide as workflow_module

    original = workflow_module.draft_to_slide
    first = _draft(["短", "也短"])
    second = _draft(["改写内容"])

    def convert(slide_id, layout_id, draft):
        if draft is second:
            raise ValueError("private-material")
        return original(slide_id, layout_id, draft)

    monkeypatch.setattr(workflow_module, "draft_to_slide", convert)
    generator = ScriptedGenerator([first, second])
    slide, issues = await run_slide_workflow(
        build_slide_workflow(generator), _payload(), uuid.uuid4()
    )

    assert slide.blocks[1].items == ["短", "也短"]
    assert any(issue.code == "repair_failed" for issue in issues)


@pytest.mark.asyncio
async def test_workflow_propagates_cancellation_during_repair() -> None:
    repair_started = asyncio.Event()

    class BlockingRepairGenerator(ScriptedGenerator):
        async def generate(self, payload: SlideGenerationInput) -> SlideDraft:
            if payload.issues:
                self.prompts.append(list(payload.issues))
                repair_started.set()
                await asyncio.Event().wait()
            return await super().generate(payload)

    generator = BlockingRepairGenerator([_draft(["短", "也短"])])
    task = asyncio.create_task(
        run_slide_workflow(build_slide_workflow(generator), _payload(), uuid.uuid4())
    )
    await asyncio.wait_for(repair_started.wait(), timeout=5)
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task

    assert len(generator.prompts) == 2


def test_error_diagnostics_include_json_location_without_content() -> None:
    try:
        json.loads('{"text":"private\nmaterial"}')
    except json.JSONDecodeError as cause:
        error = InvalidSlideOutputError("private-provider-response")
        error.__cause__ = cause
        details = safe_error_details(error)

    assert details["error_code"] == "invalid_output"
    assert details["cause_type"] == "JSONDecodeError"
    assert details["json_line"] == 1
    assert "private" not in json.dumps(details)
