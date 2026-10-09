import asyncio
import logging
import time
import uuid
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
from app.models.project import Project
from app.schemas.outline import OutlineErrorCode, OutlineEvent, OutlineStage
from app.services.outline_inputs import project_input_signature
from app.services.outline_progress import publish_outline_event
from app.services.topic_material import topic_request_from_sections
from app.worker.context import create_outline_generator
from app.worker.retry import retry_after_failure
from app.workflows.outline import build_outline_workflow, run_outline_workflow

__all__ = ["create_outline_generator", "generate_outline"]

logger = logging.getLogger(__name__)


async def generate_outline(ctx: dict[str, Any], project_id: str, job_id: str) -> None:
    project_uuid = uuid.UUID(project_id)
    current_stage: OutlineStage = "load_input"
    try:
        load_started = await _stage_started(
            project_uuid,
            job_id,
            "load_input",
            10,
            "正在读取输入材料",
        )
        from app.services.travel_research import ensure_project_research

        async def research_progress(value: int, message: str):
            await _progress(
                project_uuid,
                10 + value // 10,
                message,
                stage="travel_research",
                stage_status="started",
            )

        await ensure_project_research(
            project_uuid, model=ctx.get("chat_model"), progress=research_progress
        )
        loaded = await _load_generation_input(project_uuid, job_id)
        if loaded is None:
            logger.warning(
                "outline stage skipped project_id=%s job_id=%s stage=load_input reason=stale_job",
                project_id,
                job_id,
            )
            return
        await _stage_succeeded(
            project_uuid,
            job_id,
            "load_input",
            20,
            "输入材料读取完成",
            load_started,
        )
        payload, input_signature, expected_revision = loaded

        current_stage = "plan_structure"
        plan_started = await _stage_started(
            project_uuid,
            job_id,
            "plan_structure",
            25,
            "正在规划大纲结构",
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
        )

        current_stage = "validate"
        validate_started = await _stage_started(
            project_uuid,
            job_id,
            "validate",
            80,
            "正在校验大纲结构",
        )
        pages = [OutlinePage(**page.model_dump()) for page in draft.pages]
        await _stage_succeeded(
            project_uuid,
            job_id,
            "validate",
            88,
            "大纲结构校验通过",
            validate_started,
        )

        current_stage = "save"
        save_started = await _stage_started(
            project_uuid,
            job_id,
            "save",
            92,
            "正在保存大纲",
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
        )
        if revision is None:
            logger.warning(
                "outline stage skipped project_id=%s job_id=%s stage=save reason=stale_job",
                project_id,
                job_id,
            )
            return
        await _stage_succeeded(
            project_uuid,
            job_id,
            "save",
            98,
            "大纲保存完成",
            save_started,
        )
    except asyncio.CancelledError:
        # ARQ 的 job_timeout/abort 会取消协程；取消前也要落库，否则前端会永久显示 generating。
        error_code: OutlineErrorCode = (
            "model_timeout" if current_stage == "plan_structure" else "unknown"
        )
        try:
            await _save_failed(project_uuid, job_id, error_code, stage=current_stage)
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
        retry = retry_after_failure(ctx, error)
        await _stage_failed(
            project_uuid,
            job_id,
            current_stage,
            error_code,
            retrying=retry is not None,
        )
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
        await _save_failed(project_uuid, job_id, error_code, stage=current_stage)
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
        ),
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
) -> int | None:
    async with async_session_factory() as session:
        result = await session.execute(
            select(Project)
            .options(selectinload(Project.outline))
            .where(Project.id == project_id)
            .with_for_update()
        )
        project = result.scalar_one()
        outline = project.outline
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
        outline.revision += 1
        project.status = "draft"
        await session.commit()
        return outline.revision


async def _save_failed(
    project_id: uuid.UUID,
    job_id: str,
    error_code: OutlineErrorCode,
    *,
    stage: OutlineStage,
) -> None:
    async with async_session_factory() as session:
        result = await session.execute(
            select(Project)
            .options(selectinload(Project.outline))
            .where(Project.id == project_id)
            .with_for_update()
        )
        project = result.scalar_one_or_none()
        if (
            project is None
            or project.outline is None
            or project.outline.job_id != job_id
            or project.outline.status != "generating"
        ):
            return
        project.outline.status = "failed"
        project.outline.error_code = error_code
        project.outline.error = _public_error(error_code)
        await session.commit()

    await publish_outline_event(
        project_id,
        OutlineEvent(
            type="failed",
            status="failed",
            progress=100,
            message="大纲生成失败",
            stage=stage,
            stage_status="failed",
            error_code=error_code,
        ),
    )


async def _stage_started(
    project_id: uuid.UUID,
    job_id: str,
    stage: OutlineStage,
    progress: int,
    message: str,
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
        progress,
        message,
        stage=stage,
        stage_status="started",
    )
    return started_at


async def _stage_succeeded(
    project_id: uuid.UUID,
    job_id: str,
    stage: OutlineStage,
    progress: int,
    message: str,
    started_at: float,
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
        progress,
        message,
        stage=stage,
        stage_status="succeeded",
    )


async def _stage_failed(
    project_id: uuid.UUID,
    job_id: str,
    stage: OutlineStage,
    error_code: OutlineErrorCode,
    *,
    retrying: bool,
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
        30 if retrying else 100,
        "AI 服务响应异常，正在重试" if retrying else "大纲生成失败",
        stage=stage,
        stage_status="failed",
        error_code=error_code,
    )


async def _progress(
    project_id: uuid.UUID,
    progress: int,
    message: str,
    *,
    stage: OutlineStage | None = None,
    stage_status: str | None = None,
    error_code: OutlineErrorCode | None = None,
) -> None:
    await publish_outline_event(
        project_id,
        OutlineEvent(
            type="progress",
            status="generating",
            progress=progress,
            message=message,
            stage=stage,
            stage_status=stage_status,  # type: ignore[arg-type]
            error_code=error_code,
        ),
    )


def _error_code(error: Exception, stage: OutlineStage) -> OutlineErrorCode:
    if isinstance(error, LLMNotConfiguredError):
        return "llm_not_configured"
    if isinstance(error, (LLMTimeoutError, TimeoutError, httpx.TimeoutException)):
        return "model_timeout"
    if isinstance(error, InvalidModelOutputError) and stage == "plan_structure":
        return "invalid_model_output"
    if isinstance(error, LLMUnavailableError):
        return "model_unavailable"
    if stage == "load_input":
        return "input_load_failed"
    if stage == "validate":
        return "invalid_outline"
    if stage == "save":
        return "save_failed"
    if stage == "plan_structure":
        return "model_unavailable"
    return "unknown"


def _public_error(error_code: OutlineErrorCode) -> str:
    # 只保存不含供应商响应、堆栈和输入材料的通用文案，详细原因留在后端日志。
    return "模型生成大纲失败，请稍后重试"
