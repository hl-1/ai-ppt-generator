import logging
import uuid
from datetime import UTC, datetime

from redis.exceptions import RedisError
from sqlalchemy import select

from app.core.db import async_session_factory
from app.models.project import ProjectOutline
from app.schemas.outline import (
    OutlineEvent,
    OutlineExecution,
    OutlineHistoryEntry,
    OutlineStageExecution,
)
from app.services.events import EventStream
from app.services.outline_errors import outline_failure

outline_events: EventStream[OutlineEvent] = EventStream("outline", OutlineEvent)
logger = logging.getLogger(__name__)


def new_execution(job_id: str, *, travel: bool, max_attempts: int) -> OutlineExecution:
    now = datetime.now(UTC)
    stages = ["queue", "load_input"]
    if travel:
        stages.append("travel_research")
    stages.extend(["plan_structure", "validate", "save"])
    execution = OutlineExecution(
        job_id=job_id,
        started_at=now,
        updated_at=now,
        max_attempts=max_attempts,
        stages=[OutlineStageExecution(stage=stage) for stage in stages],
    )
    return apply_event(
        execution,
        OutlineEvent(
            type="progress",
            status="generating",
            progress=0,
            stage="queue",
            stage_status="started",
            message="正在提交生成任务",
            timestamp=now,
            max_attempts=max_attempts,
        ),
    )


def apply_event(execution: OutlineExecution, event: OutlineEvent) -> OutlineExecution:
    execution = execution.model_copy(deep=True)
    now = event.timestamp or datetime.now(UTC)
    execution.updated_at = now
    execution.status = event.status
    late_queue_ack = event.stage == "queue" and execution.stage != "queue"
    if not late_queue_ack:
        execution.attempt = event.attempt
        execution.retry_at = event.retry_at
    # Queue acknowledgement can arrive after the worker has already started.
    if event.stage and not (event.stage == "queue" and execution.stage != "queue"):
        execution.stage = event.stage
    if event.attempt > max((step.attempt for step in execution.stages), default=1):
        for step in execution.stages:
            if step.stage != "queue":
                step.status, step.message = "pending", "等待重新执行"
                step.started_at = step.finished_at = None
                step.error_code, step.issues = None, []
    if event.stage == "load_input" and event.stage_status == "started":
        queue = execution.stages[0]
        if queue.status in {"pending", "started"}:
            queue.status = "succeeded"
            queue.message, queue.finished_at = "任务已进入队列并开始执行", now
    if event.stage:
        step = next((step for step in execution.stages if step.stage == event.stage), None)
        if step and event.stage_status:
            if event.stage_status == "started" and step.status != "started":
                step.started_at, step.finished_at = now, None
            if event.stage_status in {"succeeded", "partial", "failed", "retrying", "cancelled"}:
                step.finished_at = now
            step.status, step.message, step.attempt = (
                event.stage_status,
                event.message,
                event.attempt,
            )
            step.error_code, step.issues = event.error_code, event.issues
    if not late_queue_ack:
        execution.failure = (
            outline_failure(event.error_code, event.stage)
            if event.error_code and event.stage
            else None
        )
    if event.type in {"completed", "failed", "cancelled"}:
        execution.finished_at, execution.retry_at = now, None
    execution.history.append(
        OutlineHistoryEntry(
            timestamp=now,
            stage=event.stage,
            status=event.stage_status,
            message=event.message,
            attempt=event.attempt,
            error_code=event.error_code,
        )
    )
    execution.history = execution.history[-80:]
    return execution


async def publish_outline_event(project_id: uuid.UUID, event: OutlineEvent) -> bool:
    async with async_session_factory() as session:
        outline = await session.scalar(
            select(ProjectOutline)
            .where(
                ProjectOutline.project_id == project_id,
            )
            .with_for_update()
        )
        if outline is None or not event.job_id or outline.job_id != event.job_id:
            return False
        allowed = (
            outline.status == "generating"
            or (
                outline.status == "draft"
                and event.stage == "save"
                and event.stage_status == "succeeded"
            )
            or (outline.status == event.status and event.type in {"failed", "cancelled"})
        )
        if not allowed:
            return False
        if outline.execution:
            execution = OutlineExecution.model_validate(outline.execution)
            if execution.finished_at:
                if (
                    event.type not in {"completed", "failed", "cancelled"}
                    or event.status != execution.status
                ):
                    return False
                event.timestamp = execution.updated_at
            else:
                event.timestamp = datetime.now(UTC)
                execution = apply_event(execution, event)
                outline.execution = execution.model_dump(mode="json")
            event.execution = execution
        await session.commit()
    try:
        await outline_events.publish(project_id, event)
    except RedisError:
        # HTTP polling still exposes the durable execution if SSE transport is down.
        logger.warning("outline progress delivery failed project_id=%s", project_id)
    return True
