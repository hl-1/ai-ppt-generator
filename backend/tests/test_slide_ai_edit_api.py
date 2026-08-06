import uuid
from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.db import async_session_factory
from app.domain.slide_patch import BulletsPatch, TextPatch
from app.llm.base import SlideEditInput
from app.llm.errors import LLMNotConfiguredError
from app.main import app
from app.models.project import Project, ProjectOutline
from app.models.slide import Slide as SlideRow


@pytest.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as value:
        yield value


async def _sign_up(client: AsyncClient) -> dict[str, str]:
    response = await client.post(
        "/api/v1/auth/register",
        json={"email": f"ai_edit_{uuid.uuid4().hex}@example.com", "password": "password123"},
    )
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _bullets_blocks(*, locked_title: bool = False) -> list[dict]:
    return [
        {
            "id": "t1",
            "slot_id": "title",
            "type": "text",
            "text": "原标题",
            "locked": locked_title,
        },
        {
            "id": "b1",
            "slot_id": "body",
            "type": "bullets",
            "items": ["要点一", "要点二"],
            "locked": False,
        },
    ]


async def _project_with_slide(
    client: AsyncClient,
    headers: dict[str, str],
    *,
    blocks: list[dict] | None = None,
    status: str = "ready",
    revision: int = 1,
) -> tuple[dict, SlideRow]:
    response = await client.post(
        "/api/v1/projects",
        json={"title": "AI 局部修改", "page_count": 5, "audience": "管理层"},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    project = response.json()

    async with async_session_factory() as session:
        result = await session.execute(
            select(Project)
            .options(selectinload(Project.outline))
            .where(Project.id == uuid.UUID(project["id"]))
        )
        record = result.scalar_one()
        page_id = uuid.uuid4()
        row = SlideRow(
            project_id=record.id,
            outline_page_id=page_id,
            position=1,
            layout_id="bullets",
            title="要点页",
            status=status,
            blocks=blocks or _bullets_blocks(),
            issues=[],
            revision=revision,
        )
        session.add(row)
        session.add(
            ProjectOutline(
                project_id=record.id,
                status="confirmed",
                pages=[
                    {
                        "id": str(page_id),
                        "title": "要点页",
                        "objective": "目标",
                        "key_points": ["要点"],
                        "source_refs": [],
                        "layout_id": "bullets",
                    }
                ],
                revision=2,
            )
        )
        record.status = "ready"
        await session.commit()
        await session.refresh(row)
        return project, row


class ScriptedEditGenerator:
    def __init__(self, operations: list | None = None, *, error: Exception | None = None) -> None:
        self.operations = operations or [
            TextPatch(block_id="t1", text="改写后的标题"),
            BulletsPatch(block_id="b1", items=["改写要点一", "改写要点二"]),
        ]
        self.error = error
        self.seen_block_ids: list[list[str]] = []
        self.seen_payloads: list[SlideEditInput] = []

    async def generate(self, payload: SlideEditInput):
        self.seen_payloads.append(payload)
        self.seen_block_ids.append([block.block_id for block in payload.blocks])
        if self.error is not None:
            raise self.error
        return list(self.operations)


@pytest.mark.asyncio
async def test_propose_instruct_requires_instruction(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.api.v1.decks.create_slide_edit_generator",
        lambda: ScriptedEditGenerator(),
    )
    headers = await _sign_up(client)
    project, slide = await _project_with_slide(client, headers)

    response = await client.post(
        f"/api/v1/projects/{project['id']}/deck/slides/{slide.id}/ai-edit",
        headers=headers,
        json={"action": "instruct", "revision": slide.revision},
    )
    assert response.status_code == 422

    blank = await client.post(
        f"/api/v1/projects/{project['id']}/deck/slides/{slide.id}/ai-edit",
        headers=headers,
        json={"action": "instruct", "instruction": "   ", "revision": slide.revision},
    )
    assert blank.status_code == 422


@pytest.mark.asyncio
async def test_propose_instruct_returns_before_after(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    generator = ScriptedEditGenerator(
        operations=[TextPatch(block_id="t1", text="按指令改过的标题")]
    )
    monkeypatch.setattr(
        "app.api.v1.decks.create_slide_edit_generator",
        lambda: generator,
    )
    headers = await _sign_up(client)
    project, slide = await _project_with_slide(client, headers)

    response = await client.post(
        f"/api/v1/projects/{project['id']}/deck/slides/{slide.id}/ai-edit",
        headers=headers,
        json={
            "action": "instruct",
            "instruction": "标题改得更正式",
            "revision": slide.revision,
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["revision"] == slide.revision
    assert len(body["operations"]) == 1
    title_op = body["operations"][0]
    assert title_op["before"]["text"] == "原标题"
    assert title_op["after"]["text"] == "按指令改过的标题"
    assert generator.seen_payloads[0].action == "instruct"
    assert generator.seen_payloads[0].instruction == "标题改得更正式"


@pytest.mark.asyncio
async def test_propose_returns_before_after(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    generator = ScriptedEditGenerator()
    monkeypatch.setattr(
        "app.api.v1.decks.create_slide_edit_generator",
        lambda: generator,
    )
    headers = await _sign_up(client)
    project, slide = await _project_with_slide(client, headers)

    response = await client.post(
        f"/api/v1/projects/{project['id']}/deck/slides/{slide.id}/ai-edit",
        headers=headers,
        json={"action": "rewrite", "revision": slide.revision},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["revision"] == slide.revision
    assert len(body["operations"]) == 2
    title_op = next(item for item in body["operations"] if item["block_id"] == "t1")
    assert title_op["before"]["text"] == "原标题"
    assert title_op["after"]["text"] == "改写后的标题"
    assert title_op["slot_id"] == "title"


@pytest.mark.asyncio
async def test_propose_excludes_locked_blocks_from_model(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    generator = ScriptedEditGenerator(operations=[BulletsPatch(block_id="b1", items=["仅改正文"])])
    monkeypatch.setattr(
        "app.api.v1.decks.create_slide_edit_generator",
        lambda: generator,
    )
    headers = await _sign_up(client)
    project, slide = await _project_with_slide(
        client,
        headers,
        blocks=_bullets_blocks(locked_title=True),
    )

    response = await client.post(
        f"/api/v1/projects/{project['id']}/deck/slides/{slide.id}/ai-edit",
        headers=headers,
        json={"action": "condense", "revision": slide.revision},
    )
    assert response.status_code == 200, response.text
    assert generator.seen_block_ids[0] == ["b1"]
    body = response.json()
    assert all(item["block_id"] != "t1" for item in body["operations"])


@pytest.mark.asyncio
async def test_propose_revision_conflict(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.api.v1.decks.create_slide_edit_generator",
        lambda: ScriptedEditGenerator(),
    )
    headers = await _sign_up(client)
    project, slide = await _project_with_slide(client, headers)

    response = await client.post(
        f"/api/v1/projects/{project['id']}/deck/slides/{slide.id}/ai-edit",
        headers=headers,
        json={"action": "expand", "revision": slide.revision - 1},
    )
    assert response.status_code == 409
    assert "刷新" in response.json()["detail"]


@pytest.mark.asyncio
async def test_propose_rejects_while_generating(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.api.v1.decks.create_slide_edit_generator",
        lambda: ScriptedEditGenerator(),
    )
    headers = await _sign_up(client)
    project, slide = await _project_with_slide(client, headers, status="generating")

    response = await client.post(
        f"/api/v1/projects/{project['id']}/deck/slides/{slide.id}/ai-edit",
        headers=headers,
        json={"action": "rewrite", "revision": slide.revision},
    )
    assert response.status_code == 409
    assert "生成中" in response.json()["detail"]


@pytest.mark.asyncio
async def test_propose_llm_not_configured(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.api.v1.decks.create_slide_edit_generator",
        lambda: ScriptedEditGenerator(
            error=LLMNotConfiguredError("未配置 LLM API Key，无法局部修改页面")
        ),
    )
    headers = await _sign_up(client)
    project, slide = await _project_with_slide(client, headers)

    response = await client.post(
        f"/api/v1/projects/{project['id']}/deck/slides/{slide.id}/ai-edit",
        headers=headers,
        json={"action": "rewrite", "revision": slide.revision},
    )
    assert response.status_code == 503
    assert "未配置 LLM API Key" in response.json()["detail"]


@pytest.mark.asyncio
async def test_apply_updates_content_without_locking(
    client: AsyncClient,
) -> None:
    headers = await _sign_up(client)
    project, slide = await _project_with_slide(client, headers)

    response = await client.post(
        f"/api/v1/projects/{project['id']}/deck/slides/{slide.id}/ai-edit/apply",
        headers=headers,
        json={
            "revision": slide.revision,
            "operations": [
                {"block_id": "t1", "type": "text", "text": "AI 改过的标题"},
                {
                    "block_id": "b1",
                    "type": "bullets",
                    "items": ["很长" * 30, "另一条也很长" * 20],
                },
            ],
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["revision"] == slide.revision + 1
    by_id = {block["id"]: block for block in body["blocks"]}
    assert by_id["t1"]["text"] == "AI 改过的标题"
    assert by_id["t1"]["locked"] is False
    assert by_id["b1"]["locked"] is False
    assert any(issue["severity"] == "warning" for issue in body["issues"])


@pytest.mark.asyncio
async def test_apply_skips_locked_blocks(client: AsyncClient) -> None:
    headers = await _sign_up(client)
    project, slide = await _project_with_slide(
        client,
        headers,
        blocks=_bullets_blocks(locked_title=True),
    )

    response = await client.post(
        f"/api/v1/projects/{project['id']}/deck/slides/{slide.id}/ai-edit/apply",
        headers=headers,
        json={
            "revision": slide.revision,
            "operations": [
                {"block_id": "t1", "type": "text", "text": "不应覆盖"},
                {"block_id": "b1", "type": "bullets", "items": ["可改"]},
            ],
        },
    )
    assert response.status_code == 200
    body = response.json()
    by_id = {block["id"]: block for block in body["blocks"]}
    assert by_id["t1"]["text"] == "原标题"
    assert by_id["t1"]["locked"] is True
    assert by_id["b1"]["items"] == ["可改"]
    assert by_id["b1"]["locked"] is False
