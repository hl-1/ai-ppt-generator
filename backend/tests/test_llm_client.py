import json

import httpx
import pytest
from langchain_openai import ChatOpenAI
from pydantic import BaseModel

from app.domain.slide_draft import FlexSlideDraft, SlideDraft
from app.llm.base import OutlineGenerationInput
from app.llm.client import StructuredChatClient
from app.llm.deepseek import DeepSeekOutlineGenerator
from app.llm.errors import InvalidModelOutputError, LLMTimeoutError
from app.llm.relayout import RelayoutTreesDraft


class _Result(BaseModel):
    text: str


@pytest.fixture
async def mock_model():
    clients = []

    def build(content, *, finish_reason="stop"):
        def respond(request):
            body = json.loads(request.content)
            assert body["response_format"] == {"type": "json_object"}
            if isinstance(content, Exception):
                raise content
            return httpx.Response(
                200,
                json={
                    "id": "test-completion",
                    "object": "chat.completion",
                    "created": 0,
                    "model": "test-model",
                    "choices": [
                        {
                            "index": 0,
                            "finish_reason": finish_reason,
                            "message": {"role": "assistant", "content": content},
                        }
                    ],
                },
            )

        client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
        clients.append(client)
        return ChatOpenAI(
            model="test-model",
            api_key="test-key",
            base_url="https://model.test/v1",
            http_async_client=client,
            max_retries=0,
        )

    yield build
    for client in clients:
        await client.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "content",
    [
        '{"text":"ok"}',
        '```json\n{"text":"ok"}\n```',
        [{"type": "text", "text": '{"text":"ok"}'}],
    ],
)
async def test_client_decodes_supported_json_wrappers(mock_model, content) -> None:
    client = StructuredChatClient(model=mock_model(content), api_key="test-key")

    result = await client.complete(_Result, system="Return JSON", user="Test", purpose="test")

    assert result.text == "ok"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "content,finish_reason",
    [
        ('{"text":"ok"', "stop"),
        ('{"text":"ok"}', "length"),
    ],
)
async def test_client_rejects_truncated_output(mock_model, content, finish_reason) -> None:
    client = StructuredChatClient(
        model=mock_model(content, finish_reason=finish_reason), api_key="test-key"
    )

    with pytest.raises(InvalidModelOutputError):
        await client.complete(_Result, system="Return JSON", user="Test", purpose="test")


@pytest.mark.asyncio
async def test_client_reports_validation_path_without_input_content(mock_model) -> None:
    client = StructuredChatClient(
        model=mock_model('{"text":{"private":"source material"}}'), api_key="test-key"
    )

    with pytest.raises(InvalidModelOutputError) as caught:
        await client.complete(_Result, system="Return JSON", user="Test", purpose="test")

    assert "text: string_type" in str(caught.value)
    assert "source material" not in str(caught.value)


@pytest.mark.asyncio
async def test_client_preserves_timeout_classification(mock_model) -> None:
    client = StructuredChatClient(
        model=mock_model(httpx.ReadTimeout("test timeout")), api_key="test-key"
    )

    with pytest.raises(LLMTimeoutError):
        await client.complete(_Result, system="Return JSON", user="Test", purpose="test")


@pytest.mark.asyncio
async def test_outline_normalizes_raw_model_output_before_business_validation(mock_model) -> None:
    response = [
        {
            "title": "Overview",
            "objective": "Explain the topic",
            "keyPoints": ["First finding", "Second finding"],
            "layoutId": "unsupported-model-layout",
            "pageRole": "BODY",
            "evidence": None,
        }
    ]
    generator = DeepSeekOutlineGenerator(
        model=mock_model(f"```json\n{json.dumps(response)}\n```"),
        api_key="test-key",
        layout_ids=frozenset({"bullets"}),
    )

    draft = await generator.generate(
        OutlineGenerationInput(title="Overview", tone="professional", page_count=1)
    )

    assert draft.pages[0].title == "Overview"
    assert draft.pages[0].key_points == ["First finding", "Second finding"]
    assert draft.pages[0].layout_id == "bullets"
    assert draft.pages[0].evidence == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "schema,payload",
    [
        (
            SlideDraft,
            {
                "blocks": [{"type": "text", "slot_id": "title", "text": "Overview\nDetails"}],
                "speaker_notes": "Notes",
            },
        ),
        (
            FlexSlideDraft,
            {
                "blocks": [{"type": "text", "id": "title", "text": "Overview"}],
                "layout_tree": {
                    "type": "column",
                    "id": "root",
                    "children": [{"type": "block", "id": "leaf", "block_id": "title"}],
                },
            },
        ),
        (
            RelayoutTreesDraft,
            {
                "trees": [
                    {
                        "type": "row",
                        "id": "root",
                        "children": [{"type": "block", "id": "leaf", "block_id": "title"}],
                    }
                ],
            },
        ),
    ],
)
async def test_shared_client_preserves_slide_and_relayout_contracts(mock_model, schema, payload):
    client = StructuredChatClient(model=mock_model(json.dumps(payload)), api_key="test-key")

    result = await client.complete(schema, system="Return JSON", user="Test", purpose="test")

    assert result.model_dump(exclude_unset=True) == payload
