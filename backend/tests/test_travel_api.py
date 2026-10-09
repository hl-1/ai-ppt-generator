import uuid
from unittest.mock import AsyncMock

import httpx
import pytest
from sqlalchemy import select

from app.api.deps import get_queue
from app.core.db import async_session_factory
from app.main import app
from app.models.project import Project
from app.schemas.travel import ResearchData
from app.services.travel_research import create_research, execute_research


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
