import json
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from app.api.v1 import outlines
from app.domain.layout import get_layout
from app.llm.base import OutlineGenerationInput, OutlineSourceSection, SlideGenerationInput
from app.llm.deepseek import DeepSeekOutlineGenerator
from app.llm.slide import DeepSeekSlideGenerator
from app.services.topic_material import build_topic_document, topic_request_from_sections
from app.worker import tasks
from app.workflows.outline import prepare_outline_input

TOPIC = "春节去北京旅游规划"
LONG_TOPIC = (
    TOPIC + "\n" + "希望覆盖景点预约、交通、住宿、春节活动和冬季保暖。" * 7 + "避免每天更换酒店。"
)


@pytest.mark.parametrize("topic", [TOPIC, LONG_TOPIC, "幼儿园垃圾分类教学"])
def test_topic_material_preserves_input_without_business_metrics(topic):
    document = build_topic_document(topic=topic)

    assert len(document.sections) == 1
    assert document.sections[0].text == topic
    assert document.char_count == len(topic)
    assert topic_request_from_sections([s.model_dump() for s in document.sections]) == topic


def test_extracts_original_topic_from_legacy_material():
    sections = [
        {
            "heading": "样稿说明",
            "text": f"本材料为围绕“{TOPIC}”自动生成的模拟汇报素材，适用于样稿。",
        },
        {"heading": "对象对比", "text": "岗位需求指数：算法工程86分。"},
    ]

    assert topic_request_from_sections(sections) == TOPIC
    assert topic_request_from_sections([], fallback=TOPIC) == TOPIC


async def test_regeneration_replaces_legacy_topic_before_enqueue(monkeypatch):
    source = SimpleNamespace(
        id=uuid.uuid4(),
        kind="topic",
        char_count=100,
        sections=[
            {"heading": "样稿说明", "text": f"本材料为围绕“{TOPIC}”自动生成的模拟汇报素材。"},
            {"heading": "对象对比", "text": "岗位需求指数：算法工程86分。"},
        ],
    )
    text_source = SimpleNamespace(kind="text", char_count=4, sections=[{"text": "补充要求"}])
    project = SimpleNamespace(
        id=uuid.uuid4(),
        title="项目简称",
        sources=[source, text_source],
        outline=SimpleNamespace(status="draft", revision=1),
    )
    session = AsyncMock()
    queue = AsyncMock()
    monkeypatch.setattr(outlines, "publish_outline_event", AsyncMock())

    async def enqueue(*args, **kwargs):
        session.commit.assert_awaited_once()
        assert len(source.sections) == 1
        assert source.sections[0]["text"] == TOPIC
        return object()

    queue.enqueue_job.side_effect = enqueue
    accepted = await outlines.generate_outline(project, session, queue)

    assert source.char_count == len(TOPIC)
    assert source.project_id == project.id
    assert "通用知识" in source.warnings[0]
    assert text_source.sections == [{"text": "补充要求"}]
    assert accepted.job_id == project.outline.job_id


async def test_outline_worker_loads_full_topic_independent_of_title(monkeypatch):
    document = build_topic_document(topic=LONG_TOPIC)
    project = SimpleNamespace(
        id=uuid.uuid4(),
        title=TOPIC,
        audience=None,
        tone="professional",
        page_count=5,
        sources=[
            SimpleNamespace(
                id=uuid.uuid4(), kind="topic", sections=[s.model_dump() for s in document.sections]
            )
        ],
        outline=SimpleNamespace(job_id="job", status="generating", revision=1),
    )
    session = AsyncMock()
    session.execute.return_value = Mock(scalar_one_or_none=Mock(return_value=project))
    factory = Mock(return_value=session)
    session.__aenter__.return_value = session
    monkeypatch.setattr(tasks, "async_session_factory", factory)

    payload, _, _ = await tasks._load_generation_input(project.id, "job")

    assert payload.title == TOPIC
    assert payload.topic_request == LONG_TOPIC
    assert payload.sections[0].text == LONG_TOPIC


def test_outline_prompt_keeps_full_topic_and_neutral_example():
    generator = DeepSeekOutlineGenerator.__new__(DeepSeekOutlineGenerator)
    generator._layout_ids = frozenset({"cover", "bullets", "chart"})
    payload = OutlineGenerationInput(
        title=TOPIC,
        tone="professional",
        page_count=5,
        topic_mode=True,
        topic_request=LONG_TOPIC,
        report_brief={"scenario": "business_review"},
        sections=[OutlineSourceSection(ref="S1:1", level=1, text=LONG_TOPIC, locator="主题")],
    )
    prepared = prepare_outline_input(payload, max_section_chars=60)
    user = generator._user_prompt(prepared)
    body = json.loads(user[user.index("{") :])

    assert body["topic_request"] == LONG_TOPIC
    assert len(body["sections"][0]["text"]) == 60
    assert "允许使用模拟素材" not in user
    system = generator._system_prompt(prepared)
    assert '"narrative": ["主题背景", "核心内容", "总结建议"]' in system
    assert "主题生成约束" in system
    assert "每页必须有相关的具体内容" in system


@pytest.mark.parametrize("mode", ["fixed", "flex"])
def test_slide_prompts_receive_complete_topic_even_without_source_refs(mode):
    generator = DeepSeekSlideGenerator.__new__(DeepSeekSlideGenerator)
    payload = SlideGenerationInput(
        deck_title=TOPIC,
        tone="professional",
        position=2,
        total_pages=5,
        page_title="景点预约",
        objective="安排春节游览",
        key_points=["故宫预约", "提前核对春节开放安排"],
        layout_id="bullets",
        layout_mode=mode,
        topic_mode=True,
        topic_request=LONG_TOPIC,
        sections=[],
    )
    prompt = (
        generator._user_prompt(payload, get_layout("bullets"))
        if mode == "fixed"
        else generator._flex_user_prompt(payload)
    )
    body = json.loads(prompt[prompt.index("{") :])

    assert body["topic_request"] == LONG_TOPIC
    assert body["sections"] == []
    assert "主题生成约束" in prompt
    assert "数据是模拟素材" not in prompt
    if mode == "flex":
        assert "主题生成约束" in generator._flex_system_prompt(payload)
