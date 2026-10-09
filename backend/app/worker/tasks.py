import asyncio
import logging
import time
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.db import async_session_factory
from app.domain.outline import OutlinePage
from app.llm.base import OutlineGenerationInput, OutlineGenerator, OutlineSourceSection
from app.llm.errors import (
    InvalidModelOutputError,
    LLMNotConfiguredError,
    LLMTimeoutError,
    LLMUnavailableError,
)
from app.models.project import Project, ProjectOutline
from app.schemas.outline import (
    OutlineErrorCode,
    OutlineEvent,
    OutlineExecution,
    OutlineIssue,
    OutlineStage,
    OutlineStageStatus,
)
from app.services.outline_errors import outline_failure, travel_service_issue
from app.services.outline_inputs import project_input_signature
from app.services.outline_progress import apply_event, publish_outline_event
from app.services.topic_material import topic_request_from_sections
from app.worker.context import create_outline_generator
from app.worker.retry import MAX_TRIES, retry_after_failure
from app.workflows.outline import build_outline_workflow, run_outline_workflow

__all__ = ["create_outline_generator", "generate_outline"]

logger = logging.getLogger(__name__)


class OutlineRunStopped(asyncio.CancelledError):
    """The run was cancelled or superseded at a persistence checkpoint."""


async def generate_outline(ctx: dict[str, Any], project_id: str, job_id: str) -> None:
    project_uuid = uuid.UUID(project_id)
    attempt = int(ctx.get("job_try", 1))
    current_stage: OutlineStage = "load_input"
    try:
        load_started = await _stage_started(
            project_uuid,
            job_id,
            "load_input",
            10,
            "正在读取输入材料",
            attempt=attempt,
        )
        travel = await _is_active_travel_project(project_uuid, job_id)
        if travel is None:
            return
        loaded = None if travel else await _load_generation_input(project_uuid, job_id)
        await _stage_succeeded(
            project_uuid,
            job_id,
            "load_input",
            20,
            "输入材料读取完成",
            load_started,
            attempt=attempt,
        )
        if travel:
            from app.services.travel_research import ensure_project_research

            current_stage = "travel_research"
            research_started = await _stage_started(
                project_uuid,
                job_id,
                current_stage,
                20,
                "正在查询旅行资料",
                attempt=attempt,
            )

            async def research_progress(value: int, message: str):
                await _progress(
                    project_uuid,
                    job_id,
                    20 + value // 10,
                    message,
                    stage="travel_research",
                    stage_status="started",
                    attempt=attempt,
                )

            await ensure_project_research(
                project_uuid,
                model=ctx.get("chat_model"),
                progress=research_progress,
            )
            partial, message, issues = await _research_outcome(project_uuid)
            await _stage_succeeded(
                project_uuid,
                job_id,
                current_stage,
                30,
                message,
                research_started,
                attempt=attempt,
                partial=partial,
                issues=issues,
            )
            current_stage = "load_input"
            loaded = await _load_generation_input(project_uuid, job_id)
        if loaded is None:
            return
        payload, input_signature, expected_revision = loaded

        current_stage = "plan_structure"
        plan_started = await _stage_started(
            project_uuid,
            job_id,
            "plan_structure",
            25,
            "正在规划大纲结构",
            attempt=attempt,
        )
        generator: OutlineGenerator = ctx["outline_generator"]
        workflow = build_outline_workflow(generator)
        draft = await run_outline_workflow(workflow, payload)
        await _stage_succeeded(
            project_uuid,
            job_id,
            "plan_structure",
            75,
            "大纲结构规划完成",
            plan_started,
            attempt=attempt,
        )

        current_stage = "validate"
        validate_started = await _stage_started(
            project_uuid,
            job_id,
            "validate",
            80,
            "正在校验大纲结构",
            attempt=attempt,
        )
        pages = [OutlinePage(**page.model_dump()) for page in draft.pages]
        await _stage_succeeded(
            project_uuid,
            job_id,
            "validate",
            88,
            "大纲结构校验通过",
            validate_started,
            attempt=attempt,
        )

        current_stage = "save"
        await _stage_started(
            project_uuid,
            job_id,
            "save",
            92,
            "正在保存大纲",
            attempt=attempt,
        )
        revision = await _save_completed(
            project_uuid,
            job_id,
            pages,
            input_signature,
            expected_revision,
            blueprint=draft.blueprint.model_dump(mode="json"),
            travel_research_id=uuid.UUID(payload.travel_context["research_id"])
            if payload.travel_context
            else None,
            attempt=attempt,
        )
        if revision is None:
            logger.warning(
                "outline stage skipped project_id=%s job_id=%s stage=save reason=stale_job",
                project_id,
                job_id,
            )
            return
    except OutlineRunStopped:
        return
    except asyncio.CancelledError:
        # ARQ 的 job_timeout/abort 会取消协程；取消前也要落库，否则前端会永久显示 generating。
        error_code: OutlineErrorCode = (
            "model_timeout"
            if current_stage == "plan_structure"
            else "travel_timeout"
            if current_stage == "travel_research"
            else "unknown"
        )
        try:
            await _save_failed(
                project_uuid, job_id, error_code, stage=current_stage, attempt=attempt
            )
        except Exception:
            logger.exception(
                "outline cancellation cleanup failed project_id=%s job_id=%s stage=%s",
                project_id,
                job_id,
                current_stage,
            )
        raise
    except Exception as error:
        error_code = _error_code(error, current_stage)
        retry = (
            retry_after_failure(ctx, error)
            if outline_failure(error_code, current_stage).retryable
            else None
        )
        try:
            await _stage_failed(
                project_uuid,
                job_id,
                current_stage,
                error_code,
                retrying=retry is not None,
                attempt=attempt,
                retry_at=datetime.now(UTC) + timedelta(milliseconds=retry.defer_score or 0)
                if retry is not None
                else None,
            )
        except OutlineRunStopped:
            return
        logger.exception(
            "outline stage failed project_id=%s job_id=%s stage=%s "
            "error_code=%s job_try=%s error=%s",
            project_id,
            job_id,
            current_stage,
            error_code,
            ctx.get("job_try", 1),
            error,
        )
        if retry is not None:
            raise retry from error
        await _save_failed(project_uuid, job_id, error_code, stage=current_stage, attempt=attempt)
        return

    await publish_outline_event(
        project_uuid,
        OutlineEvent(
            type="completed",
            status="draft",
            progress=100,
            message="大纲已生成",
            revision=revision,
            stage="save",
            stage_status="succeeded",
            job_id=job_id,
            attempt=attempt,
            max_attempts=MAX_TRIES,
        ),
    )


async def _is_active_travel_project(project_id: uuid.UUID, job_id: str) -> bool | None:
    from app.services.travel_research import is_travel

    async with async_session_factory() as session:
        project = await session.get(Project, project_id)
        if (
            not project
            or not project.outline
            or project.outline.job_id != job_id
            or project.outline.status != "generating"
        ):
            return None
        if not project.sources or not any(source.char_count > 0 for source in project.sources):
            raise ValueError("No usable input")
        return is_travel(project)


async def _research_outcome(project_id: uuid.UUID) -> tuple[bool, str, list[OutlineIssue]]:
    from app.services.travel_research import current_research

    async with async_session_factory() as session:
        project = await session.get(Project, project_id)
        research = await current_research(session, project) if project else None
        if not research or research.stale or research.status not in {"ready", "partial"}:
            raise ValueError("Travel research is unavailable")
        data = research.data or {}
        issues = [
            travel_service_issue(item["service"], item.get("error_code"))
            for item in data.get("services", [])
            if item["status"] != "ready"
        ]
        issues.extend(
            OutlineIssue(
                code=item["code"],
                message=f"{item['stage']}：{item['message']}",
                action=item["action"],
            )
            for item in data.get("issues", [])
        )
        if research.error_code and not data.get("issues"):
            code = (
                "travel_timeout" if "timeout" in research.error_code else "travel_research_failed"
            )
            failure = outline_failure(code, "travel_research")
            issues.append(OutlineIssue(code=code, message=failure.message, action=failure.action))
        unresolved = (data.get("plan") or {}).get("unresolved_items", [])
        if unresolved:
            issues.append(
                OutlineIssue(
                    code="unverified_items",
                    message=f"仍有 {len(unresolved)} 项信息待核实",
                    action="请在旅行资料中查看待核实事项，确认后再用于出行。",
                )
            )
        partial = research.status == "partial"
        count = len(data.get("sources", []))
        return (
            partial,
            f"已获取 {count} 条来源" + ("，部分信息待核实" if partial else "，旅行资料查询完成"),
            issues,
        )


async def _load_generation_input(
    project_id: uuid.UUID,
    job_id: str,
) -> tuple[OutlineGenerationInput, str, int] | None:
    async with async_session_factory() as session:
        result = await session.execute(
            select(Project)
            .options(selectinload(Project.sources), selectinload(Project.outline))
            .where(Project.id == project_id)
        )
        project = result.scalar_one_or_none()
        if (
            project is None
            or project.outline is None
            or project.outline.job_id != job_id
            or project.outline.status != "generating"
        ):
            return None

        sections = [
            OutlineSourceSection(
                ref=f"S{source_index}:{section_index}",
                heading=section.get("heading"),
                level=section.get("level", 0),
                text=section.get("text", ""),
                locator=section.get("locator", ""),
            )
            for source_index, source in enumerate(project.sources, start=1)
            for section_index, section in enumerate(source.sections, start=1)
        ]
        from app.domain.content_density import normalize_density
        from app.services.travel_planning import travel_context, travel_sections
        from app.services.travel_research import current_research, is_travel

        research = await current_research(session, project) if is_travel(project) else None
        travel = travel_context(research, project.travel_booking_states)
        if is_travel(project) and travel is None:
            raise ValueError("旅行资料已失效，请刷新后重新生成")
        sections.extend(travel_sections(research))

        payload = OutlineGenerationInput(
            travel_context=travel,
            report_brief=getattr(project, "report_brief", None) or {},
            title=project.title,
            audience=project.audience,
            tone=project.tone,
            page_count=project.page_count,
            content_density=normalize_density(getattr(project, "content_density", None)),
            topic_mode=any(source.kind == "topic" for source in project.sources),
            topic_request="\n\n".join(
                topic_request_from_sections(source.sections, fallback=project.title)
                for source in project.sources
                if source.kind == "topic"
            )
            or None,
            sections=sections,
        )
        return payload, project_input_signature(project), project.outline.revision


async def _save_completed(
    project_id: uuid.UUID,
    job_id: str,
    pages: list[OutlinePage],
    input_signature: str,
    expected_revision: int,
    *,
    blueprint: dict | None = None,
    travel_research_id: uuid.UUID | None = None,
    attempt: int = 1,
) -> int | None:
    async with async_session_factory() as session:
        result = await session.execute(
            select(Project)
            .options(selectinload(Project.outline))
            .where(Project.id == project_id)
            .with_for_update()
        )
        project = result.scalar_one()
        outline = await session.scalar(
            select(ProjectOutline)
            .where(
                ProjectOutline.project_id == project_id,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if (
            outline is None
            or outline.job_id != job_id
            or outline.status != "generating"
            or outline.revision != expected_revision
        ):
            # 用户已经启动了更新任务时，迟到结果必须丢弃，不能覆盖新状态。
            return None

        if project_input_signature(project) != input_signature:
            raise ValueError("生成期间输入已修改，请重新生成大纲")

        outline.pages = [page.model_dump(mode="json") for page in pages]
        outline.blueprint = blueprint or {}
        outline.input_signature = input_signature
        outline.travel_research_id = travel_research_id
        outline.status = "draft"
        outline.error = None
        outline.error_code = None
        outline.revision += 1
        if outline.execution:
            outline.execution = apply_event(
                OutlineExecution.model_validate(outline.execution),
                OutlineEvent(
                    type="completed",
                    status="draft",
                    progress=100,
                    job_id=job_id,
                    message=f"已生成并保存 {len(pages)} 页大纲",
                    stage="save",
                    stage_status="succeeded",
                    revision=outline.revision,
                    attempt=attempt,
                ),
            ).model_dump(mode="json")
        project.status = "draft"
        await session.commit()
        return outline.revision


async def _save_failed(
    project_id: uuid.UUID,
    job_id: str,
    error_code: OutlineErrorCode,
    *,
    stage: OutlineStage,
    attempt: int = 1,
) -> None:
    async with async_session_factory() as session:
        result = await session.execute(
            select(Project)
            .options(selectinload(Project.outline))
            .where(Project.id == project_id)
            .with_for_update()
        )
        project = result.scalar_one_or_none()
        outline = await session.scalar(
            select(ProjectOutline)
            .where(
                ProjectOutline.project_id == project_id,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if (
            project is None
            or outline is None
            or outline.job_id != job_id
            or outline.status != "generating"
        ):
            return
        outline.status = "failed"
        outline.error_code = error_code
        outline.error = outline_failure(error_code, stage).message
        if outline.execution:
            outline.execution = apply_event(
                OutlineExecution.model_validate(outline.execution),
                OutlineEvent(
                    type="failed",
                    status="failed",
                    progress=100,
                    job_id=job_id,
                    message=outline.error,
                    stage=stage,
                    stage_status="failed",
                    error_code=error_code,
                    attempt=attempt,
                ),
            ).model_dump(mode="json")
        await session.commit()

    await publish_outline_event(
        project_id,
        OutlineEvent(
            type="failed",
            status="failed",
            progress=100,
            message=outline_failure(error_code, stage).message,
            stage=stage,
            stage_status="failed",
            error_code=error_code,
            job_id=job_id,
            attempt=attempt,
            max_attempts=MAX_TRIES,
        ),
    )


async def _stage_started(
    project_id: uuid.UUID,
    job_id: str,
    stage: OutlineStage,
    progress: int,
    message: str,
    *,
    attempt: int = 1,
) -> float:
    started_at = time.monotonic()
    logger.info(
        "outline stage started project_id=%s job_id=%s stage=%s progress=%s",
        project_id,
        job_id,
        stage,
        progress,
    )
    await _progress(
        project_id,
        job_id,
        progress,
        message,
        stage=stage,
        stage_status="started",
        attempt=attempt,
    )
    return started_at


async def _stage_succeeded(
    project_id: uuid.UUID,
    job_id: str,
    stage: OutlineStage,
    progress: int,
    message: str,
    started_at: float,
    *,
    attempt: int = 1,
    partial: bool = False,
    issues: list[OutlineIssue] | None = None,
) -> None:
    duration_ms = int((time.monotonic() - started_at) * 1000)
    logger.info(
        "outline stage succeeded project_id=%s job_id=%s stage=%s duration_ms=%s",
        project_id,
        job_id,
        stage,
        duration_ms,
    )
    await _progress(
        project_id,
        job_id,
        progress,
        message,
        stage=stage,
        stage_status="partial" if partial else "succeeded",
        attempt=attempt,
        issues=issues,
    )


async def _stage_failed(
    project_id: uuid.UUID,
    job_id: str,
    stage: OutlineStage,
    error_code: OutlineErrorCode,
    *,
    retrying: bool,
    attempt: int = 1,
    retry_at: datetime | None = None,
) -> None:
    logger.warning(
        "outline stage failed project_id=%s job_id=%s stage=%s error_code=%s retrying=%s",
        project_id,
        job_id,
        stage,
        error_code,
        retrying,
    )
    await _progress(
        project_id,
        job_id,
        30 if retrying else 100,
        outline_failure(error_code, stage).message,
        stage=stage,
        stage_status="retrying" if retrying else "failed",
        error_code=error_code,
        attempt=attempt,
        retry_at=retry_at,
    )


async def _progress(
    project_id: uuid.UUID,
    job_id: str,
    progress: int,
    message: str,
    *,
    stage: OutlineStage | None = None,
    stage_status: OutlineStageStatus | None = None,
    error_code: OutlineErrorCode | None = None,
    attempt: int = 1,
    retry_at: datetime | None = None,
    issues: list[OutlineIssue] | None = None,
) -> None:
    accepted = await publish_outline_event(
        project_id,
        OutlineEvent(
            type="progress",
            status="generating",
            progress=progress,
            message=message,
            stage=stage,
            stage_status=stage_status,
            error_code=error_code,
            job_id=job_id,
            attempt=attempt,
            max_attempts=MAX_TRIES,
            retry_at=retry_at,
            issues=issues or [],
        ),
    )
    if accepted is False:
        raise OutlineRunStopped()


def _error_code(error: Exception, stage: OutlineStage) -> OutlineErrorCode:
    if stage == "travel_research":
        return (
            "travel_timeout"
            if isinstance(error, (TimeoutError, httpx.TimeoutException))
            else "travel_research_failed"
        )
    if stage == "load_input":
        return "input_load_failed"
    if stage == "validate":
        return "invalid_outline"
    if stage == "save":
        return "save_failed"
    current: BaseException | None = error
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        status_code = getattr(current, "status_code", None)
        if isinstance(current, httpx.HTTPStatusError):
            status_code = current.response.status_code
        if status_code in {401, 403}:
            return "model_auth_failed"
        if status_code == 429:
            return "model_rate_limited"
        if status_code in {400, 404, 422}:
            return "model_request_rejected"
        current = current.__cause__ or current.__context__
    if isinstance(error, LLMNotConfiguredError):
        return "llm_not_configured"
    if isinstance(error, (LLMTimeoutError, TimeoutError, httpx.TimeoutException)):
        return "model_timeout"
    if isinstance(error, InvalidModelOutputError) and stage == "plan_structure":
        return "invalid_model_output"
    if isinstance(error, LLMUnavailableError):
        return "model_unavailable"
    if stage == "plan_structure":
        return "model_unavailable"
    return "unknown"
