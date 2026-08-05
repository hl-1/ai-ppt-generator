import uuid
from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.deps import get_queue
from app.api.v1.outlines import _encode_sse
from app.core.db import async_session_factory
from app.domain.outline import OutlineDraft, OutlinePageDraft
from app.llm.base import OutlineGenerationInput
from app.main import app
from app.models.project import Project, ProjectOutline
from app.schemas.outline import OutlineEvent
from app.services.outline_inputs import project_input_signature
from app.worker.tasks import generate_outline


class FakeQueue:
    def __init__(self) -> None:
        self.calls: list[tuple] = []

    async def enqueue_job(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return object()


@pytest.fixture
async def queue(monkeypatch: pytest.MonkeyPatch) -> AsyncGenerator[FakeQueue, None]:
    fake = FakeQueue()

    async def ignore_progress(*_args, **_kwargs) -> None:
        pass

    monkeypatch.setattr("app.api.v1.outlines.publish_outline_event", ignore_progress)
    monkeypatch.setattr("app.worker.tasks.publish_outline_event", ignore_progress)
    app.dependency_overrides[get_queue] = lambda: fake
    yield fake
    app.dependency_overrides.pop(get_queue, None)


@pytest.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as value:
        yield value


async def _sign_up(client: AsyncClient) -> dict[str, str]:
    response = await client.post(
        "/api/v1/auth/register",
        json={"email": f"outline_{uuid.uuid4().hex}@example.com", "password": "password123"},
    )
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def _project(
    client: AsyncClient,
    headers: dict[str, str],
    *,
    with_source: bool = True,
) -> dict:
    response = await client.post(
        "/api/v1/projects",
        json={"title": "平台化复盘", "page_count": 5},
        headers=headers,
    )
    project = response.json()
    if with_source:
        await client.post(
            f"/api/v1/projects/{project['id']}/sources",
            json={"kind": "topic", "content": "把内部工具沉淀为平台能力"},
            headers=headers,
        )
    return project


def _pages(count: int = 5) -> list[dict]:
    return [
        {
            "id": str(uuid.uuid4()),
            "title": f"第 {index} 页",
            "objective": "说明本页的核心目标",
            "key_points": ["要点一", "要点二"],
            "source_refs": ["S1:1"],
            "layout_id": "cover" if index == 1 else "bullets",
        }
        for index in range(1, count + 1)
    ]


class FakeGenerator:
    async def generate(self, payload: OutlineGenerationInput) -> OutlineDraft:
        return OutlineDraft(
            pages=[
                OutlinePageDraft(
                    title=f"第 {index} 页",
                    objective="说明本页的核心目标",
                    key_points=["要点一", "要点二"],
                    source_refs=["S1:1"],
                    layout_id="cover" if index == 1 else "bullets",
                )
                for index in range(1, payload.page_count + 1)
            ]
        )


async def _complete_outline(project_id: str) -> ProjectOutline:
    async with async_session_factory() as session:
        result = await session.execute(
            select(Project)
            .options(selectinload(Project.sources), selectinload(Project.outline))
            .where(Project.id == uuid.UUID(project_id))
        )
        project = result.scalar_one()
        assert project.outline is not None
        project.outline.status = "draft"
        project.outline.pages = _pages()
        project.outline.input_signature = project_input_signature(project)
        project.outline.revision += 1
        await session.commit()
        await session.refresh(project.outline)
        return project.outline


@pytest.mark.asyncio
async def test_generate_outline_enqueues_unique_job(
    client: AsyncClient,
    queue: FakeQueue,
) -> None:
    headers = await _sign_up(client)
    project = await _project(client, headers)

    response = await client.post(
        f"/api/v1/projects/{project['id']}/outline/generate",
        headers=headers,
    )

    assert response.status_code == 202
    assert response.json()["status"] == "generating"
    args, kwargs = queue.calls[0]
    assert args[0] == "generate_outline"
    assert args[1] == project["id"]
    assert kwargs["_job_id"] == response.json()["job_id"]

    outline = await client.get(
        f"/api/v1/projects/{project['id']}/outline",
        headers=headers,
    )
    assert outline.json()["status"] == "generating"


@pytest.mark.asyncio
async def test_worker_saves_generated_outline(
    client: AsyncClient,
    queue: FakeQueue,
) -> None:
    headers = await _sign_up(client)
    project = await _project(client, headers)
    accepted = await client.post(
        f"/api/v1/projects/{project['id']}/outline/generate",
        headers=headers,
    )
    job_id = accepted.json()["job_id"]

    await generate_outline(
        {"outline_generator": FakeGenerator(), "job_try": 1},
        project["id"],
        job_id,
    )

    response = await client.get(
        f"/api/v1/projects/{project['id']}/outline",
        headers=headers,
    )
    outline = response.json()
    assert outline["status"] == "draft"
    assert len(outline["pages"]) == 5
    assert outline["revision"] == 2


@pytest.mark.asyncio
async def test_generate_requires_source(
    client: AsyncClient,
    queue: FakeQueue,
) -> None:
    headers = await _sign_up(client)
    project = await _project(client, headers, with_source=False)
    response = await client.post(
        f"/api/v1/projects/{project['id']}/outline/generate",
        headers=headers,
    )
    assert response.status_code == 422
    assert queue.calls == []


@pytest.mark.asyncio
async def test_outline_edit_confirm_unlock_flow(
    client: AsyncClient,
    queue: FakeQueue,
) -> None:
    headers = await _sign_up(client)
    project = await _project(client, headers)
    await client.post(f"/api/v1/projects/{project['id']}/outline/generate", headers=headers)
    outline = await _complete_outline(project["id"])

    updated = await client.patch(
        f"/api/v1/projects/{project['id']}/outline",
        json={"revision": outline.revision, "pages": _pages()},
        headers=headers,
    )
    assert updated.status_code == 200

    confirmed = await client.post(
        f"/api/v1/projects/{project['id']}/outline/confirm",
        json={"revision": updated.json()["revision"]},
        headers=headers,
    )
    assert confirmed.status_code == 200
    assert confirmed.json()["status"] == "confirmed"

    blocked = await client.patch(
        f"/api/v1/projects/{project['id']}",
        json={"title": "不应静默改变"},
        headers=headers,
    )
    assert blocked.status_code == 409

    unlocked = await client.post(
        f"/api/v1/projects/{project['id']}/outline/unconfirm",
        json={"revision": confirmed.json()["revision"]},
        headers=headers,
    )
    assert unlocked.status_code == 200
    assert unlocked.json()["status"] == "draft"

    changed = await client.patch(
        f"/api/v1/projects/{project['id']}",
        json={"title": "解锁后可以修改"},
        headers=headers,
    )
    assert changed.status_code == 200


@pytest.mark.asyncio
async def test_confirm_rejects_stale_input_and_revision(
    client: AsyncClient,
    queue: FakeQueue,
) -> None:
    headers = await _sign_up(client)
    project = await _project(client, headers)
    await client.post(f"/api/v1/projects/{project['id']}/outline/generate", headers=headers)
    outline = await _complete_outline(project["id"])

    stale_revision = await client.post(
        f"/api/v1/projects/{project['id']}/outline/confirm",
        json={"revision": outline.revision - 1},
        headers=headers,
    )
    assert stale_revision.status_code == 409

    await client.patch(
        f"/api/v1/projects/{project['id']}",
        json={"audience": "新的受众"},
        headers=headers,
    )
    stale_input = await client.post(
        f"/api/v1/projects/{project['id']}/outline/confirm",
        json={"revision": outline.revision},
        headers=headers,
    )
    assert stale_input.status_code == 409
    assert "重新生成" in stale_input.json()["detail"]


@pytest.mark.asyncio
async def test_outline_is_isolated_between_users(
    client: AsyncClient,
    queue: FakeQueue,
) -> None:
    owner = await _sign_up(client)
    other = await _sign_up(client)
    project = await _project(client, owner)

    response = await client.post(
        f"/api/v1/projects/{project['id']}/outline/generate",
        headers=other,
    )
    assert response.status_code == 404


def test_sse_encoding_has_event_and_json_data() -> None:
    encoded = _encode_sse(
        OutlineEvent(
            type="progress",
            status="generating",
            progress=25,
            message="正在规划",
        )
    )
    assert encoded.startswith("event: progress\ndata: {")
    assert encoded.endswith("\n\n")
