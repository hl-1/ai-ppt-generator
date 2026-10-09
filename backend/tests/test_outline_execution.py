import asyncio
import uuid
from types import SimpleNamespace

import httpx
import pytest
from arq import Retry
from redis.exceptions import RedisError

from app.core.db import async_session_factory
from app.models.project import Project
from app.schemas.outline import OutlineEvent
from app.services.outline_progress import publish_outline_event
from app.worker.tasks import _error_code, generate_outline
from tests.test_outlines_api import (
    BrokenGenerator,
    FakeGenerator,
    _project,
    _sign_up,
    _start_generating,
    client,
    queue,
)

__all__ = ["client", "queue"]


async def _get(client, headers, project):
    response = await client.get(f"/api/v1/projects/{project['id']}/outline", headers=headers)
    assert response.status_code == 200
    return response.json()


async def test_execution_survives_reload_and_completes_with_saved_pages(client, queue):
    headers = await _sign_up(client)
    project, job_id = await _start_generating(client, headers)
    await generate_outline({"outline_generator": FakeGenerator()}, project["id"], job_id)
    outline = await _get(client, headers, project)
    execution = outline["execution"]
    assert execution["job_id"] == job_id
    assert execution["status"] == "draft"
    assert execution["finished_at"]
    assert len(outline["pages"]) == 5
    assert all(step["status"] == "succeeded" for step in execution["stages"])
    assert execution["history"][-1]["message"] == "已生成并保存 5 页大纲"
    assert (await _get(client, headers, project))["execution"] == execution


async def test_worker_finishing_before_queue_ack_keeps_all_stages_complete(
    client, queue, monkeypatch
):
    async def immediate(_function, project_id, job_id, **kwargs):
        await generate_outline({"outline_generator": FakeGenerator()}, project_id, job_id)
        return object()

    monkeypatch.setattr(queue, "enqueue_job", immediate)
    headers = await _sign_up(client)
    project = await _project(client, headers)
    response = await client.post(
        f"/api/v1/projects/{project['id']}/outline/generate", headers=headers
    )
    assert response.status_code == 202
    outline = await _get(client, headers, project)
    assert outline["status"] == "draft"
    assert all(step["status"] == "succeeded" for step in outline["execution"]["stages"])


async def test_retry_feedback_records_attempt_and_then_clears_failure(client, queue):
    headers = await _sign_up(client)
    project, job_id = await _start_generating(client, headers)
    with pytest.raises(Retry):
        await generate_outline(
            {"outline_generator": BrokenGenerator(), "job_try": 1}, project["id"], job_id
        )
    retry = (await _get(client, headers, project))["execution"]
    assert retry["status"] == "generating"
    assert retry["retry_at"]
    assert retry["failure"]["stage"] == "plan_structure"
    assert retry["stages"][2]["status"] == "retrying"
    await generate_outline(
        {"outline_generator": FakeGenerator(), "job_try": 2}, project["id"], job_id
    )
    completed = (await _get(client, headers, project))["execution"]
    assert completed["attempt"] == 2
    assert completed["failure"] is None
    assert completed["retry_at"] is None
    assert any(entry["error_code"] == "invalid_model_output" for entry in completed["history"])


async def test_final_failure_has_action_and_does_not_claim_retry(client, queue):
    headers = await _sign_up(client)
    project, job_id = await _start_generating(client, headers)
    await generate_outline(
        {"outline_generator": BrokenGenerator(), "job_try": 2}, project["id"], job_id
    )
    execution = (await _get(client, headers, project))["execution"]
    assert execution["status"] == "failed"
    assert execution["retry_at"] is None
    assert execution["finished_at"]
    assert execution["failure"]["stage"] == "plan_structure"
    assert execution["failure"]["action"]
    assert "非法 layout_id" not in str(execution)


@pytest.mark.parametrize("rejected", [False, True])
async def test_queue_failure_is_persisted(client, queue, monkeypatch, rejected):
    async def fail(*args, **kwargs):
        if rejected:
            return None
        raise RedisError("unavailable")

    monkeypatch.setattr(queue, "enqueue_job", fail)
    headers = await _sign_up(client)
    project = await _project(client, headers)
    response = await client.post(
        f"/api/v1/projects/{project['id']}/outline/generate", headers=headers
    )
    assert response.status_code == 503
    outline = await _get(client, headers, project)
    assert outline["status"] == "failed"
    assert outline["execution"]["failure"]["stage"] == "queue"


async def test_cancelled_run_cannot_save_a_late_result(client, queue, monkeypatch):
    async def abort(*args, **kwargs):
        return True

    monkeypatch.setattr("app.api.v1.outlines.Job.abort", abort)
    headers = await _sign_up(client)
    project, job_id = await _start_generating(client, headers)
    started, release = asyncio.Event(), asyncio.Event()

    class SlowGenerator(FakeGenerator):
        async def generate(self, payload):
            started.set()
            await release.wait()
            return await super().generate(payload)

    task = asyncio.create_task(
        generate_outline({"outline_generator": SlowGenerator()}, project["id"], job_id)
    )
    try:
        await asyncio.wait_for(started.wait(), 10)
        response = await client.post(
            f"/api/v1/projects/{project['id']}/outline/cancel", headers=headers
        )
        assert response.status_code == 200
        assert response.json()["execution"]["status"] == "cancelled"
    finally:
        release.set()
        await task
    outline = await _get(client, headers, project)
    assert outline["status"] == "cancelled"
    assert outline["pages"] == []
    assert outline["execution"]["stage"] == "plan_structure"
    assert not await publish_outline_event(
        uuid.UUID(project["id"]),
        OutlineEvent(
            type="progress",
            status="generating",
            progress=50,
            message="Late event",
            job_id=job_id,
        ),
    )


async def test_new_run_ignores_previous_job_progress(client, queue):
    headers = await _sign_up(client)
    project, old_job_id = await _start_generating(client, headers)
    await generate_outline(
        {"outline_generator": BrokenGenerator(), "job_try": 2}, project["id"], old_job_id
    )
    response = await client.post(
        f"/api/v1/projects/{project['id']}/outline/generate", headers=headers
    )
    new_job_id = response.json()["job_id"]
    assert new_job_id != old_job_id
    assert not await publish_outline_event(
        uuid.UUID(project["id"]),
        OutlineEvent(
            type="failed",
            status="failed",
            progress=100,
            message="Old failure",
            job_id=old_job_id,
        ),
    )
    execution = (await _get(client, headers, project))["execution"]
    assert execution["job_id"] == new_job_id
    assert execution["failure"] is None
    assert not any(entry["message"] == "Old failure" for entry in execution["history"])


async def test_queue_error_after_cancellation_preserves_cancelled_state(client, queue, monkeypatch):
    async def abort(*args, **kwargs):
        return True

    monkeypatch.setattr("app.api.v1.outlines.Job.abort", abort)
    headers = await _sign_up(client)
    project = await _project(client, headers)

    async def enqueue(*args, **kwargs):
        stopped = await client.post(
            f"/api/v1/projects/{project['id']}/outline/cancel", headers=headers
        )
        assert stopped.status_code == 200
        raise RedisError("queue failed after cancellation")

    monkeypatch.setattr(queue, "enqueue_job", enqueue)
    response = await asyncio.wait_for(
        client.post(
            f"/api/v1/projects/{project['id']}/outline/generate",
            headers=headers,
        ),
        10,
    )
    assert response.status_code == 503
    assert (await _get(client, headers, project))["execution"]["status"] == "cancelled"


async def test_travel_timeout_is_attributed_to_research(client, queue, monkeypatch):
    headers = await _sign_up(client)
    project = await _project(client, headers)
    async with async_session_factory() as session:
        stored = await session.get(Project, uuid.UUID(project["id"]))
        stored.report_brief = {"scenario": "travel_plan"}
        stored.travel_conditions = {"destination": "北京", "confirmed": True}
        await session.commit()

    async def timeout(*args, **kwargs):
        raise TimeoutError("sensitive provider response")

    monkeypatch.setattr("app.services.travel_research.ensure_project_research", timeout)
    response = await client.post(
        f"/api/v1/projects/{project['id']}/outline/generate", headers=headers
    )
    assert response.status_code == 202
    await generate_outline(
        {"outline_generator": FakeGenerator(), "job_try": 2},
        project["id"],
        response.json()["job_id"],
    )
    execution = (await _get(client, headers, project))["execution"]
    assert execution["failure"]["stage"] == "travel_research"
    assert execution["failure"]["code"] == "travel_timeout"
    assert "sensitive" not in str(execution)


async def test_partial_research_exposes_service_and_substage(client, queue, monkeypatch):
    from app.worker.tasks import _research_outcome

    headers = await _sign_up(client)
    project = await _project(client, headers)

    async def research(*args):
        return SimpleNamespace(
            stale=False,
            status="partial",
            error_code="total_timeout",
            data={
                "sources": [{"id": "source"}],
                "services": [
                    {"service": "firecrawl", "status": "failed", "error_code": "http_429"}
                ],
                "issues": [
                    {
                        "stage": "检索官网",
                        "code": "total_timeout",
                        "message": "查询超时",
                        "action": "请重新查询",
                    }
                ],
                "plan": {"unresolved_items": ["门票待核实"]},
            },
        )

    monkeypatch.setattr("app.services.travel_research.current_research", research)
    partial, message, issues = await _research_outcome(uuid.UUID(project["id"]))
    assert partial and "1 条来源" in message
    assert issues[0].service == "firecrawl"
    assert "额度不足" in issues[0].message
    assert "检索官网" in issues[1].message


@pytest.mark.parametrize(
    "stage,expected",
    [
        ("load_input", "input_load_failed"),
        ("travel_research", "travel_timeout"),
        ("save", "save_failed"),
    ],
)
def test_timeout_codes_match_the_stage(stage, expected):
    assert _error_code(TimeoutError(), stage) == expected


@pytest.mark.parametrize(
    "status,expected",
    [(401, "model_auth_failed"), (429, "model_rate_limited"), (400, "model_request_rejected")],
)
def test_model_http_error_classification_uses_safe_status(status, expected):
    from app.llm.errors import LLMUnavailableError

    request = httpx.Request("POST", "https://example.com/v1/chat")
    provider = httpx.HTTPStatusError(
        "sensitive response", request=request, response=httpx.Response(status, request=request)
    )
    error = LLMUnavailableError("service unavailable")
    error.__cause__ = provider
    assert _error_code(error, "plan_structure") == expected
