import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import httpx
import pytest
from sqlalchemy import select

from app.api.deps import get_queue
from app.core.db import async_session_factory
from app.llm.slide import DeepSeekSlideGenerator
from app.main import app
from app.models.project import Project
from app.schemas.travel import ResearchData, TravelConditions, TravelFact, TravelPlace, TravelSource
from app.services.travel_planning import build_travel_plan
from app.services.travel_research import create_research, execute_research
from app.worker.deck_tasks import generate_deck
from app.worker.tasks import generate_outline


@pytest.fixture
async def client():
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client


async def create_trip(client):
    registered = await client.post(
        "/api/v1/auth/register",
        json={
            "email": f"travel_{uuid.uuid4().hex}@example.com",
            "password": "password123",
        },
    )
    headers = {"Authorization": f"Bearer {registered.json()['access_token']}"}
    response = await client.post(
        "/api/v1/projects",
        headers=headers,
        json={
            "title": "春节去北京旅游规划",
            "report_brief": {"scenario": "travel_plan"},
            "travel_conditions": {"destination": "北京", "confirmed": True},
        },
    )
    assert response.status_code == 201, response.text
    project = response.json()
    await client.post(
        f"/api/v1/projects/{project['id']}/sources",
        headers=headers,
        json={
            "kind": "topic",
            "content": "春节去北京旅游规划",
        },
    )
    return headers, project


async def test_research_history_survives_conditions_change(client):
    headers, project = await create_trip(client)
    async with async_session_factory() as session:
        model = await session.get(Project, uuid.UUID(project["id"]))
        research = await create_research(session, model)
        research.status = "partial"
        research.data = ResearchData().model_dump(mode="json")
        await session.commit()
        research_id = research.id
    response = await client.patch(
        f"/api/v1/projects/{project['id']}",
        headers=headers,
        json={
            "travel_conditions": {"destination": "上海", "confirmed": True},
        },
    )
    assert response.status_code == 200, response.text
    response = await client.get(
        f"/api/v1/projects/{project['id']}/travel/research", headers=headers
    )
    assert response.status_code == 200, response.text
    assert response.json()["stale"] is True
    assert response.json()["id"] == str(research_id)
    assert response.json()["conditions"]["destination"] == "北京"


async def test_missing_confirmation_blocks_outline_and_research(client):
    headers, project = await create_trip(client)
    await client.patch(
        f"/api/v1/projects/{project['id']}",
        headers=headers,
        json={
            "travel_conditions": {"destination": "北京", "confirmed": False},
        },
    )
    queue = AsyncMock()
    app.dependency_overrides[get_queue] = lambda: queue
    try:
        for path in ("outline/generate", "travel/refresh"):
            response = await client.post(
                f"/api/v1/projects/{project['id']}/{path}", headers=headers
            )
            assert response.status_code == 422
        queue.enqueue_job.assert_not_awaited()
    finally:
        app.dependency_overrides.pop(get_queue, None)


async def test_partial_research_finishes_without_configured_providers(client, monkeypatch):
    from app.core.config import Settings
    from app.services import travel_research

    monkeypatch.setattr(
        travel_research,
        "get_settings",
        lambda: Settings(
            _env_file=None,
            llm_api_key="",
            amap_api_key="",
            qweather_api_host="",
            qweather_api_key="",
            firecrawl_api_key="",
        ),
    )
    headers, project = await create_trip(client)
    async with async_session_factory() as session:
        model = await session.get(Project, uuid.UUID(project["id"]))
        research = await create_research(session, model)
        research_id = research.id
    await execute_research(research_id)
    response = await client.get(
        f"/api/v1/projects/{project['id']}/travel/research", headers=headers
    )
    result = response.json()
    assert result["status"] == "partial" and result["progress"] == 100
    assert result["data"]["plan"]["draft"] is True
    assert all(
        day["date"] is None and day["weather"]["status"] == "pending"
        for day in result["data"]["plan"]["days"]
    )
    assert result["data"]["plan"]["known_subtotal"] == "0"


async def test_research_records_are_isolated_between_users(client):
    _, project = await create_trip(client)
    intruder, _ = await create_trip(client)
    response = await client.get(
        f"/api/v1/projects/{project['id']}/travel/research", headers=intruder
    )
    assert response.status_code == 404


@pytest.mark.parametrize("page_count, expected", [(6, 1), (10, 5)])
async def test_research_queries_only_attractions_within_page_budget(
    client, monkeypatch, page_count, expected
):
    from app.core.config import Settings
    from app.services.travel_providers import TravelProviders

    monkeypatch.setattr(
        "app.services.travel_research.get_settings",
        lambda: Settings(
            _env_file=None,
            llm_api_key="",
            amap_api_key="",
            qweather_api_host="",
            qweather_api_key="",
            firecrawl_api_key="",
        ),
    )
    limits = []

    async def places(self, city, keyword, *, limit=8, hotel=False, near=None):
        if hotel or near:
            return []
        limits.append(limit)
        return [
            TravelPlace(
                id=f"p{index}", name=f"景点{index}", location="116.397,39.917", source_id="R1"
            )
            for index in range(limit)
        ]

    monkeypatch.setattr(TravelProviders, "places", places)
    headers, project = await create_trip(client)
    response = await client.patch(
        f"/api/v1/projects/{project['id']}",
        headers=headers,
        json={
            "page_count": page_count,
            "travel_conditions": {
                "destination": "北京",
                "confirmed": True,
                "video_preferences": {"enabled": False},
            },
        },
    )
    assert response.status_code == 200
    async with async_session_factory() as session:
        model = await session.get(Project, uuid.UUID(project["id"]))
        research = await create_research(session, model)
        research_id = research.id
    await execute_research(research_id)
    response = await client.get(
        f"/api/v1/projects/{project['id']}/travel/research", headers=headers
    )
    assert limits == [expected]
    assert len(response.json()["data"]["places"]) == expected
    response = await client.patch(
        f"/api/v1/projects/{project['id']}", headers=headers, json={"page_count": 8}
    )
    assert response.status_code == 200
    response = await client.get(
        f"/api/v1/projects/{project['id']}/travel/research", headers=headers
    )
    assert response.json()["stale"] is True


async def test_refresh_version_invalidates_outline_signature(client):
    from app.services.outline_inputs import project_input_signature

    _, project = await create_trip(client)
    async with async_session_factory() as session:
        model = (
            await session.execute(select(Project).where(Project.id == uuid.UUID(project["id"])))
        ).scalar_one()
        first = await create_research(session, model)
        signature = project_input_signature(model)
        first.status = "partial"
        await session.commit()
        second = await create_research(session, model)
        assert second.version == first.version + 1
        assert project_input_signature(model) != signature


async def test_travel_workers_render_compact_pages_from_saved_research(client, monkeypatch):
    queue = AsyncMock()
    app.dependency_overrides[get_queue] = lambda: queue
    monkeypatch.setattr("app.api.v1.outlines.publish_outline_event", AsyncMock())
    monkeypatch.setattr("app.worker.tasks.publish_outline_event", AsyncMock())
    try:
        headers, project = await create_trip(client)
        project_id = project["id"]
        async with async_session_factory() as session:
            model = await session.get(Project, uuid.UUID(project_id))
            research = await create_research(session, model)
            data = ResearchData(
                places=[
                    TravelPlace(id="palace", name="故宫", source_id="R1", location="116.397,39.917")
                ],
                sources=[
                    TravelSource(
                        id="R1",
                        service="firecrawl",
                        title="官方规则",
                        url="https://www.dpm.org.cn/",
                        trust="official",
                        retrieved_at=datetime.now(UTC),
                    )
                ],
                facts=[
                    TravelFact(
                        place="故宫",
                        kind="entry_process",
                        source_id="R1",
                        status="reference",
                        quote="预约后携带有效证件核验入园，按预约时段进入。" * 20,
                    )
                ],
            )
            data.plan = build_travel_plan(
                data, TravelConditions.model_validate(model.travel_conditions)
            )
            research.data, research.status = data.model_dump(mode="json"), "partial"
            await session.commit()

        accepted = await client.post(
            f"/api/v1/projects/{project_id}/outline/generate", headers=headers
        )
        assert accepted.status_code == 202, accepted.text
        outline_generator = AsyncMock()
        outline_generator.generate.side_effect = AssertionError(
            "Saved travel outline requested model generation"
        )
        await generate_outline(
            {"outline_generator": outline_generator, "job_try": 1},
            project_id,
            accepted.json()["job_id"],
        )
        response = await client.get(f"/api/v1/projects/{project_id}/outline", headers=headers)
        outline = response.json()
        assert outline["status"] == "draft", outline
        assert len(outline["pages"]) == 6
        saved = (await client.get(f"/api/v1/projects/{project_id}", headers=headers)).json()
        assert saved["page_count"] == len(outline["pages"])
        response = await client.post(
            f"/api/v1/projects/{project_id}/outline/confirm",
            headers=headers,
            json={"revision": outline["revision"]},
        )
        assert response.status_code == 200, response.text

        response = await client.post(
            f"/api/v1/projects/{project_id}/deck/generate", headers=headers, json={}
        )
        assert response.status_code == 202, response.text
        slide_ids = queue.enqueue_job.call_args.args[2]
        chat = AsyncMock()
        chat.complete.side_effect = AssertionError("Saved travel slide requested model generation")
        await generate_deck(
            {"slide_generator": DeepSeekSlideGenerator(chat=chat), "redis": queue},
            project_id,
            slide_ids,
        )
        deck = (await client.get(f"/api/v1/projects/{project_id}/deck", headers=headers)).json()
        assert deck["status"] == "ready" and deck["failed"] == 0, deck
        assert deck["ready"] == len(outline["pages"])
        assert deck["slides"][-1]["title"] == "消费成本汇总"
        assert all(
            slide["blocks"] and "旅行资料版本" in slide["speaker_notes"] for slide in deck["slides"]
        )
        assert not any(
            call.args[0] == "generate_image" for call in queue.enqueue_job.call_args_list
        )
        chat.complete.assert_not_awaited()
    finally:
        app.dependency_overrides.pop(get_queue, None)


async def test_expanded_travel_count_remains_editable_and_cannot_be_increased_arbitrarily(client):
    headers, project = await create_trip(client)
    async with async_session_factory() as session:
        model = await session.get(Project, uuid.UUID(project["id"]))
        model.page_count = 100
        await session.commit()
    response = await client.patch(
        f"/api/v1/projects/{project['id']}", headers=headers, json={"page_count": 99}
    )
    assert response.status_code == 200, response.text
    response = await client.patch(
        f"/api/v1/projects/{project['id']}", headers=headers, json={"page_count": 101}
    )
    assert response.status_code == 422, response.text
