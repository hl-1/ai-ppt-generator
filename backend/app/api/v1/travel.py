import uuid

from fastapi import APIRouter, HTTPException
from redis.exceptions import RedisError

from app.api.v1.outlines import QueueDep
from app.api.v1.projects import CurrentUser, OwnedProject, SessionDep, _ensure_outline_unlocked
from app.core.config import get_settings
from app.schemas.travel import (
    BookingUpdate,
    ConnectivityResult,
    ResearchData,
    TravelConditions,
    TravelExtractRequest,
    TravelExtractResult,
    TravelResearchAccepted,
    TravelResearchPublic,
)
from app.services.travel_providers import TravelProviders
from app.services.travel_research import (
    create_research,
    current_research,
    extract_conditions,
    is_travel,
)

router = APIRouter(tags=["travel"])


@router.post("/travel/extract", response_model=TravelExtractResult)
async def extract(body: TravelExtractRequest, _user: CurrentUser):
    try:
        return await extract_conditions(body.text)
    except Exception as error:
        raise HTTPException(503, "旅行条件提取暂不可用，请手动填写") from error


@router.get("/travel/connectivity", response_model=ConnectivityResult)
async def connectivity(_user: CurrentUser):
    import asyncio

    import httpx

    async with httpx.AsyncClient() as client:
        providers = TravelProviders(client, get_settings(), ResearchData())
        await asyncio.gather(
            providers.geocode("北京"),
            providers.weather(TravelConditions(destination="北京"), "101010100"),
            providers.call(
                "firecrawl",
                "https://api.firecrawl.dev/v2/search",
                body={"query": "故宫博物院 官网", "limit": 1},
            ),
        )
        return ConnectivityResult(services=providers.statuses())


@router.get("/projects/{project_id}/travel/research", response_model=TravelResearchPublic | None)
async def get_research(project: OwnedProject, session: SessionDep):
    research = await current_research(session, project)
    await session.commit()
    if research:
        data = ResearchData.model_validate(research.data)
        if data.plan:
            for task in data.plan.booking_tasks:
                task.user_status = (project.travel_booking_states or {}).get(task.id, "pending")
            response = TravelResearchPublic.model_validate(research)
            response.data = data
            return response
    return research


@router.post(
    "/projects/{project_id}/travel/refresh", response_model=TravelResearchAccepted, status_code=202
)
async def refresh(project: OwnedProject, session: SessionDep, queue: QueueDep):
    _ensure_outline_unlocked(project)
    if not is_travel(project):
        raise HTTPException(422, "此项目不是旅游规划")
    conditions = TravelConditions.model_validate(project.travel_conditions or {})
    if not conditions.confirmed or not conditions.destination:
        raise HTTPException(422, "请先确认旅行条件及目的地")
    if project.outline and project.outline.status == "generating":
        raise HTTPException(409, "大纲正在生成，请等待完成")
    try:
        research = await create_research(session, project)
    except ValueError as error:
        raise HTTPException(409, str(error)) from error
    job_id = f"travel-{research.id}-{uuid.uuid4().hex}"
    try:
        job = await queue.enqueue_job("generate_travel_research", str(research.id), _job_id=job_id)
        if job is None:
            raise HTTPException(409, "任务已存在")
    except (RedisError, HTTPException) as error:
        research.status, research.error_code = "failed", "queue_unavailable"
        research.progress, research.stage = 100, "任务队列不可用"
        await session.commit()
        if isinstance(error, HTTPException):
            raise
        raise HTTPException(503, "任务队列暂时不可用") from error
    return TravelResearchAccepted(job_id=job_id, research_id=research.id)


@router.patch(
    "/projects/{project_id}/travel/bookings/{task_id}", response_model=TravelResearchPublic
)
async def update_booking(
    task_id: str, body: BookingUpdate, project: OwnedProject, session: SessionDep
):
    research = await current_research(session, project)
    if research is None or research.stale:
        raise HTTPException(409, "请先刷新旅行资料")
    data = ResearchData.model_validate(research.data)
    if not data.plan or not any(task.id == task_id for task in data.plan.booking_tasks):
        raise HTTPException(404, "预约事项不存在")
    project.travel_booking_states = {
        **(project.travel_booking_states or {}),
        task_id: body.user_status,
    }
    await session.commit()
    return await get_research(project, session)
