import logging
import uuid
from typing import Annotated

from arq.connections import ArqRedis
from arq.jobs import Job
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from redis.exceptions import RedisError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_queue
from app.api.sse import event_stream_response
from app.api.v1.projects import OwnedProject
from app.core.db import get_session
from app.domain.evidence import evidence_problem, prepare_page_plan
from app.domain.layout import load_layouts
from app.domain.topic_uniqueness import find_duplicate_topic_pages
from app.llm.base import OutlineSourceSection
from app.llm.errors import InvalidOutlineOutputError, LLMNotConfiguredError
from app.models.project import Project, ProjectOutline
from app.schemas.outline import (
    OutlineEvent,
    OutlineExecution,
    OutlineGenerateAccepted,
    OutlinePageEvidenceFitRequest,
    OutlinePublic,
    OutlineRevisionRequest,
    OutlineUpdate,
)
from app.schemas.travel import TravelConditions
from app.services.deck import invalidate_outline_slides
from app.services.outline_errors import outline_failure
from app.services.outline_inputs import migrate_outline_signature, outline_input_matches
from app.services.outline_progress import (
    apply_event,
    new_execution,
    outline_events,
    publish_outline_event,
)
from app.services.sources import refresh_topic_sources
from app.services.travel_planning import travel_context, travel_sections
from app.services.travel_research import current_research, is_travel
from app.worker.context import create_outline_generator
from app.worker.retry import MAX_TRIES

router = APIRouter(prefix="/projects/{project_id}/outline", tags=["outline"])
logger = logging.getLogger(__name__)
SessionDep = Annotated[AsyncSession, Depends(get_session)]
QueueDep = Annotated[ArqRedis, Depends(get_queue)]


def _outline_or_404(project: Project) -> ProjectOutline:
    if project.outline is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="尚未生成大纲")
    return project.outline


def _ensure_revision(outline: ProjectOutline, revision: int) -> None:
    if outline.revision != revision:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="大纲已被其他操作更新，请刷新后重试",
        )


def _ensure_draft(outline: ProjectOutline) -> None:
    if outline.status != "draft":
        detail = "请先取消确认" if outline.status == "confirmed" else "当前大纲不可编辑"
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)


async def _validate_pages(project: Project, pages: list, session: AsyncSession) -> None:
    from app.schemas.project import MAX_PAGE_COUNT

    limit = max(MAX_PAGE_COUNT, project.page_count if is_travel(project) else 0)
    if len(pages) > limit:
        raise HTTPException(422, f"大纲页数不能超过 {limit} 页")
    sources = {
        f"S{i}:{j}": section.get("text", "")
        for i, source in enumerate(project.sources, 1)
        for j, section in enumerate(source.sections, 1)
    }
    if is_travel(project):
        research = await current_research(session, project)
        if (
            not research
            or research.stale
            or not project.outline
            or research.id != project.outline.travel_research_id
        ):
            raise HTTPException(409, "旅行资料已更新或失效，请重新生成大纲")
        sources.update({section.ref: section.text for section in travel_sections(research)})
        from app.services.travel_outline import travel_coverage_issues

        problems = travel_coverage_issues(pages, travel_context(research))
        if problems:
            raise HTTPException(422, "；".join(problems))
    for page in pages:
        if any(ref not in sources for ref in page.source_refs):
            raise HTTPException(status_code=422, detail=f"{page.title}：引用的来源不存在")
        for item in page.evidence:
            problem = evidence_problem(item, sources)
            if problem:
                raise HTTPException(status_code=422, detail=f"{page.title}：{problem}")
    valid_layouts = load_layouts()
    invalid = sorted({page.layout_id for page in pages if page.layout_id not in valid_layouts})
    if invalid:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"大纲包含未知布局：{'、'.join(invalid)}",
        )
    if len(pages) != project.page_count:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"大纲必须包含 {project.page_count} 页",
        )


@router.get("", response_model=OutlinePublic)
async def get_outline(project: OwnedProject) -> ProjectOutline:
    return _outline_or_404(project)


@router.post(
    "/generate",
    response_model=OutlineGenerateAccepted,
    status_code=status.HTTP_202_ACCEPTED,
)
async def generate_outline(
    project: OwnedProject,
    session: SessionDep,
    queue: QueueDep,
) -> OutlineGenerateAccepted:
    await session.execute(select(Project.id).where(Project.id == project.id).with_for_update())
    await session.refresh(project, ["outline"])
    if is_travel(project):
        conditions = TravelConditions.model_validate(project.travel_conditions or {})
        if not conditions.confirmed or not conditions.destination:
            raise HTTPException(422, "请先确认旅行条件及目的地；日期不明时可生成建议草案")
        research = await current_research(session, project)
        if research and not research.stale and research.status in {"queued", "researching"}:
            raise HTTPException(409, "旅行资料正在查询，请完成后生成大纲")
    if not project.sources or not any(source.char_count > 0 for source in project.sources):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="请先添加可用于生成大纲的输入材料",
        )
    if project.outline is not None and project.outline.status == "confirmed":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="请先取消确认")
    if project.outline is not None and project.outline.status == "generating":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="大纲正在生成")

    refresh_topic_sources(project)
    job_id = f"outline-{project.id}-{uuid.uuid4().hex}"
    outline = project.outline
    if outline is None:
        outline = ProjectOutline(project_id=project.id)
        session.add(outline)
    outline.status = "generating"
    outline.error_code = None
    outline.error = None
    outline.job_id = job_id
    outline.execution = new_execution(
        job_id,
        travel=is_travel(project),
        max_attempts=MAX_TRIES,
    ).model_dump(mode="json")
    await session.commit()

    try:
        job = await queue.enqueue_job(
            "generate_outline",
            str(project.id),
            job_id,
            _job_id=job_id,
        )
        if job is None:
            raise RedisError("Queue rejected a unique outline job")
    except RedisError as error:
        outline = await session.scalar(
            select(ProjectOutline)
            .where(
                ProjectOutline.project_id == project.id,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if outline is None:
            raise HTTPException(503, "任务队列暂时不可用") from error
        if outline.job_id == job_id and outline.status == "generating":
            outline.status = "failed"
            outline.error_code = "queue_unavailable"
            outline.error = outline_failure("queue_unavailable", "queue").message
            if outline.execution:
                outline.execution = apply_event(
                    OutlineExecution.model_validate(outline.execution),
                    OutlineEvent(
                        type="failed",
                        status="failed",
                        progress=0,
                        stage="queue",
                        stage_status="failed",
                        job_id=job_id,
                        error_code="queue_unavailable",
                        message=outline.error,
                    ),
                ).model_dump(mode="json")
        await session.commit()
        logger.exception(
            "outline stage failed project_id=%s stage=queue error_code=queue_unavailable",
            project.id,
        )
        await publish_outline_event(
            project.id,
            OutlineEvent(
                type="failed",
                status="failed",
                progress=100,
                message="大纲生成失败",
                revision=outline.revision,
                stage="queue",
                stage_status="failed",
                error_code="queue_unavailable",
                job_id=job_id,
            ),
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="任务队列暂时不可用",
        ) from error

    await publish_outline_event(
        project.id,
        OutlineEvent(
            type="progress",
            status="generating",
            progress=0,
            message="任务已进入队列",
            revision=outline.revision,
            stage="queue",
            stage_status="succeeded",
            job_id=job_id,
        ),
    )
    logger.info(
        "outline stage succeeded project_id=%s job_id=%s stage=queue",
        project.id,
        job_id,
    )
    return OutlineGenerateAccepted(job_id=job_id)


@router.post("/cancel", response_model=OutlinePublic)
async def cancel_outline(
    project: OwnedProject,
    session: SessionDep,
    queue: QueueDep,
) -> ProjectOutline:
    outline = await session.scalar(
        select(ProjectOutline)
        .where(
            ProjectOutline.project_id == project.id,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if outline is None or outline.status != "generating":
        raise HTTPException(409, "当前没有正在生成的大纲任务，请刷新状态")
    execution = OutlineExecution.model_validate(outline.execution) if outline.execution else None
    event = OutlineEvent(
        type="cancelled",
        status="cancelled",
        progress=0,
        message="本次大纲生成已取消，输入材料与已有资料仍然保留",
        job_id=outline.job_id,
        stage=execution.stage if execution else "queue",
        stage_status="cancelled",
        attempt=execution.attempt if execution else 1,
    )
    outline.status, outline.error, outline.error_code = "cancelled", None, None
    if execution:
        event.execution = apply_event(execution, event)
        event.timestamp = event.execution.updated_at
        outline.execution = event.execution.model_dump(mode="json")
    await session.commit()
    try:
        await outline_events.publish(project.id, event)
        if outline.job_id:
            await Job(outline.job_id, queue).abort(timeout=0)
    except TimeoutError:
        pass  # Abort was requested; the worker acknowledges it asynchronously.
    except RedisError:
        logger.warning("outline abort transport unavailable project_id=%s", project.id)
    except Exception as error:
        logger.warning(
            "outline abort acknowledgement failed project_id=%s error_type=%s",
            project.id,
            type(error).__name__,
        )
    await session.refresh(outline)
    return outline


@router.patch("", response_model=OutlinePublic)
async def update_outline(
    body: OutlineUpdate,
    project: OwnedProject,
    session: SessionDep,
) -> ProjectOutline:
    outline = _outline_or_404(project)
    _ensure_draft(outline)
    _ensure_revision(outline, body.revision)
    await _validate_pages(project, body.pages, session)

    sources = {
        f"S{i}:{j}": section.get("text", "")
        for i, source in enumerate(project.sources, 1)
        for j, section in enumerate(source.sections, 1)
    }
    topic_mode = any(source.kind == "topic" for source in project.sources)
    prepared_pages = [
        prepare_page_plan(page, sources, topic_mode=topic_mode) for page in body.pages
    ]
    await invalidate_outline_slides(
        session,
        project,
        prepared_pages,
        blueprint=body.blueprint.model_dump(mode="json") if body.blueprint is not None else None,
    )
    outline.pages = [page.model_dump(mode="json") for page in prepared_pages]
    if body.blueprint is not None:
        outline.blueprint = body.blueprint.model_dump(mode="json")
    outline.revision += 1
    await session.commit()
    await session.refresh(outline)
    return outline


@router.post("/pages/{page_id}/fit-evidence", response_model=OutlinePublic)
async def fit_outline_page_evidence(
    page_id: uuid.UUID,
    body: OutlinePageEvidenceFitRequest,
    project: OwnedProject,
    session: SessionDep,
) -> ProjectOutline:
    """按用户选择的图表类型，用来源材料重构一页大纲。"""
    outline = _outline_or_404(project)
    _ensure_draft(outline)
    _ensure_revision(outline, body.revision)

    pages = [_page_from_dict(item) for item in outline.pages]
    page_index = next((index for index, page in enumerate(pages) if page.id == page_id), None)
    if page_index is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="大纲页面不存在")

    source_sections: list[OutlineSourceSection] = []
    sources: dict[str, str] = {}
    for source_index, source in enumerate(project.sources, 1):
        for section_index, section in enumerate(source.sections, 1):
            ref = f"S{source_index}:{section_index}"
            text = section.get("text", "")
            sources[ref] = text
            source_sections.append(
                OutlineSourceSection(
                    ref=ref,
                    heading=section.get("heading"),
                    level=section.get("level", 0),
                    text=text,
                    locator=section.get("locator", ""),
                )
            )

    current = pages[page_index].model_copy(
        update={
            "evidence_kind": body.evidence_kind,
            "visual_type": body.visual_type,
            "planning_notes": [],
        }
    )
    if is_travel(project):
        research = await current_research(session, project)
        extra = travel_sections(research)
        source_sections.extend(extra)
        sources.update({section.ref: section.text for section in extra})
    try:
        generator = create_outline_generator()
        fitted = await generator.refit_page(current, body.evidence_kind, source_sections)
    except LLMNotConfiguredError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(error),
        ) from error
    except (InvalidOutlineOutputError, ValueError) as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="AI 无法按当前来源重构图表页面，请补充同指标、单位、时间和范围的数据",
        ) from error

    prepared = prepare_page_plan(
        fitted.model_copy(
            update={
                "evidence_kind": body.evidence_kind,
                "visual_type": body.visual_type,
            }
        ),
        sources,
    )
    if prepared.evidence_kind != body.evidence_kind:
        detail = "；".join(prepared.planning_notes) or (
            "当前来源没有足够的可比数据，无法自动重构为图表"
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=detail,
        )

    pages[page_index] = prepared
    await _validate_pages(project, pages, session)
    await invalidate_outline_slides(session, project, pages)
    outline.pages = [page.model_dump(mode="json") for page in pages]
    outline.revision += 1
    await session.commit()
    await session.refresh(outline)
    return outline


@router.post("/confirm", response_model=OutlinePublic)
async def confirm_outline(
    body: OutlineRevisionRequest,
    project: OwnedProject,
    session: SessionDep,
) -> ProjectOutline:
    outline = _outline_or_404(project)
    _ensure_draft(outline)
    _ensure_revision(outline, body.revision)
    if not outline_input_matches(project, outline.input_signature):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="生成大纲后输入材料或设置已变化，请重新生成",
        )
    # 匹配到 legacy 签名时升级为当前指纹
    migrated = migrate_outline_signature(project, outline.input_signature)
    if migrated is not None:
        outline.input_signature = migrated
    pages = [*map(_page_from_dict, outline.pages)]
    await _validate_pages(project, pages, session)
    if any(source.kind == "topic" for source in project.sources):
        duplicates = find_duplicate_topic_pages(pages, travel_mode=is_travel(project))
        if duplicates:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail={
                    "message": "主题大纲包含重复页面，请修改后再确认",
                    "issues": duplicates,
                },
            )

    outline.status = "confirmed"
    outline.revision += 1
    project.status = "outline_ready"
    await session.commit()
    await session.refresh(outline)
    return outline


@router.post("/unconfirm", response_model=OutlinePublic)
async def unconfirm_outline(
    body: OutlineRevisionRequest,
    project: OwnedProject,
    session: SessionDep,
) -> ProjectOutline:
    outline = _outline_or_404(project)
    if outline.status != "confirmed":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="大纲尚未确认")
    _ensure_revision(outline, body.revision)

    outline.status = "draft"
    outline.revision += 1
    project.status = "draft"
    await session.commit()
    await session.refresh(outline)
    return outline


def _page_from_dict(data: dict):
    from app.domain.outline import OutlinePage

    return OutlinePage.model_validate(data)


@router.get("/events")
async def stream_outline_events(
    request: Request,
    project: OwnedProject,
) -> StreamingResponse:
    outline = _outline_or_404(project)
    settled = outline.status in {"draft", "confirmed"}
    execution = OutlineExecution.model_validate(outline.execution) if outline.execution else None
    return event_stream_response(
        request,
        stream=outline_events,
        key=project.id,
        fallback=OutlineEvent(
            type="completed"
            if settled
            else outline.status
            if outline.status in {"failed", "cancelled"}
            else "snapshot",
            status=outline.status,
            progress=100 if settled or outline.status == "failed" else 0,
            message=(
                "大纲已就绪"
                if settled
                else "大纲生成失败"
                if outline.status == "failed"
                else "任务已取消"
                if outline.status == "cancelled"
                else "等待任务进度"
            ),
            revision=outline.revision,
            stage=execution.stage if execution else "save" if settled else None,
            stage_status=(
                "succeeded" if settled else "failed" if outline.status == "failed" else None
            ),
            error_code=outline.error_code,
            job_id=outline.job_id,
            execution=execution,
            timestamp=execution.updated_at if execution else outline.updated_at,
        ),
        terminal_types={"completed", "failed", "cancelled"},
        event_filter=lambda event: event.job_id == outline.job_id,
        initial_filter=lambda event: (
            event.job_id == outline.job_id
            and event.status == outline.status
            and (
                not execution
                or bool(event.execution and event.execution.updated_at >= execution.updated_at)
            )
        ),
    )
