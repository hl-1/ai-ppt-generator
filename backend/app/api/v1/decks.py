import uuid
from typing import Annotated

from arq.connections import ArqRedis
from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Request,
    Response,
    UploadFile,
    status,
)
from fastapi.responses import StreamingResponse
from redis.exceptions import RedisError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_queue
from app.api.sse import event_stream_response
from app.api.v1.projects import OwnedProject
from app.core.db import get_session
from app.images.validate import ImageRejected, validate_image
from app.models.project import Project
from app.models.slide import Slide
from app.schemas.deck import (
    DeckEvent,
    DeckGenerateAccepted,
    DeckGenerateRequest,
    DeckPublic,
    SlidePublic,
)
from app.services.deck import (
    clear_cancel,
    deck_events,
    deck_status,
    load_slides,
    request_cancel,
    sync_slides,
    to_deck_public,
)
from app.services.media import media_url, store_image

router = APIRouter(prefix="/projects/{project_id}/deck", tags=["deck"])
SessionDep = Annotated[AsyncSession, Depends(get_session)]
QueueDep = Annotated[ArqRedis, Depends(get_queue)]


def _ensure_confirmed(project: Project) -> None:
    if project.outline is None or project.outline.status != "confirmed":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="请先确认大纲再生成页面",
        )


def _ensure_idle(slides: list[Slide]) -> None:
    if any(slide.status == "generating" for slide in slides):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="页面正在生成中")


async def _enqueue(
    queue: ArqRedis,
    session: AsyncSession,
    project_id: uuid.UUID,
    slide_ids: list[uuid.UUID],
) -> str:
    # 取消标记由发起方清理：新一轮生成理应从干净状态开始，
    # 放在任务里清会与「先取消再立刻重发」的时序抢跑。
    await clear_cancel(project_id)
    job_id = f"deck-{project_id}-{uuid.uuid4().hex}"
    try:
        job = await queue.enqueue_job(
            "generate_deck",
            str(project_id),
            [str(slide_id) for slide_id in slide_ids],
            _job_id=job_id,
        )
    except RedisError as error:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="任务队列暂时不可用",
        ) from error
    if job is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="任务已存在")
    return job_id


@router.get("", response_model=DeckPublic)
async def get_deck(project: OwnedProject, session: SessionDep) -> DeckPublic:
    slides = await load_slides(session, project.id)
    return to_deck_public(project, slides)


@router.post(
    "/generate",
    response_model=DeckGenerateAccepted,
    status_code=status.HTTP_202_ACCEPTED,
)
async def generate_deck(
    body: DeckGenerateRequest,
    project: OwnedProject,
    session: SessionDep,
    queue: QueueDep,
) -> DeckGenerateAccepted:
    _ensure_confirmed(project)
    _ensure_idle(await load_slides(session, project.id))

    pending = await sync_slides(session, project, regenerate_all=body.regenerate_all)
    slides = await load_slides(session, project.id)
    if not pending:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="所有页面均已生成，如需重做请选择整份重新生成",
        )

    pending_ids = [slide.id for slide in pending]
    project.status = "generating"
    await session.commit()

    job_id = await _enqueue(queue, session, project.id, pending_ids)
    await deck_events.publish(
        project.id,
        DeckEvent(
            type="slide_started",
            status="generating",
            progress=0,
            message=f"{len(pending_ids)} 页已进入队列",
            ready=sum(1 for slide in slides if slide.status == "ready"),
            total=len(slides),
        ),
    )
    return DeckGenerateAccepted(job_id=job_id, total=len(slides), pending=len(pending_ids))


@router.post(
    "/slides/{slide_id}/retry",
    response_model=DeckGenerateAccepted,
    status_code=status.HTTP_202_ACCEPTED,
)
async def retry_slide(
    slide_id: uuid.UUID,
    project: OwnedProject,
    session: SessionDep,
    queue: QueueDep,
) -> DeckGenerateAccepted:
    _ensure_confirmed(project)
    slides = await load_slides(session, project.id)
    target = next((slide for slide in slides if slide.id == slide_id), None)
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="页面不存在")
    if target.status == "generating":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="该页正在生成中")

    # 重试等价于把这一页退回待生成，走的仍是整份生成那条路径
    target.status = "pending"
    target.blocks = []
    target.issues = []
    target.error = None
    await session.commit()

    job_id = await _enqueue(queue, session, project.id, [slide_id])
    return DeckGenerateAccepted(job_id=job_id, total=len(slides), pending=1)


@router.post("/cancel", status_code=status.HTTP_202_ACCEPTED)
async def cancel_deck(project: OwnedProject, session: SessionDep) -> Response:
    slides = await load_slides(session, project.id)
    if deck_status(slides) != "generating":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="当前没有生成任务")
    await request_cancel(project.id)
    return Response(status_code=status.HTTP_202_ACCEPTED)


@router.put(
    "/slides/{slide_id}/blocks/{block_id}/image",
    response_model=SlidePublic,
)
async def replace_slide_image(
    slide_id: uuid.UUID,
    block_id: str,
    project: OwnedProject,
    session: SessionDep,
    file: Annotated[UploadFile, File()],
    revision: Annotated[int, Form()],
) -> Slide:
    slides = await load_slides(session, project.id)
    slide = next((item for item in slides if item.id == slide_id), None)
    if slide is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="页面不存在")

    target = next((block for block in slide.blocks if block.get("id") == block_id), None)
    if target is None or target.get("type") != "image":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="图片块不存在")

    # 页面生成完成时会整块覆盖 blocks，此时换图会被无声冲掉
    if slide.status == "generating":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="页面正在生成中，请稍后再换图",
        )

    if slide.revision != revision:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="页面已被其他操作更新，请刷新后重试",
        )

    data = await file.read()
    try:
        extension, _content_type = validate_image(data)
    except ImageRejected as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(error),
        ) from error

    key = store_image(
        user_id=project.user_id,
        project_id=project.id,
        data=data,
        extension=extension,
    )
    # 人工换过的图属于人工修改，后续 AI 修改不得覆盖
    updated = {
        **target,
        "url": media_url(key),
        "source": "upload",
        "credit": None,
        "locked": True,
    }
    # JSONB 就地改 dict 不会被 SQLAlchemy 感知，必须赋新列表
    slide.blocks = [updated if block.get("id") == block_id else block for block in slide.blocks]
    slide.revision += 1
    await session.commit()
    await session.refresh(slide)
    return SlidePublic.model_validate(slide)


@router.get("/events")
async def stream_deck_events(
    request: Request,
    project: OwnedProject,
    session: SessionDep,
) -> StreamingResponse:
    slides = await load_slides(session, project.id)
    current = deck_status(slides)
    ready = sum(1 for slide in slides if slide.status == "ready")
    failed = sum(1 for slide in slides if slide.status == "failed")
    return event_stream_response(
        request,
        stream=deck_events,
        key=project.id,
        fallback=DeckEvent(
            type="snapshot",
            status=current,
            progress=int((ready + failed) * 100 / len(slides)) if slides else 0,
            message="等待生成任务",
            ready=ready,
            failed=failed,
            total=len(slides),
        ),
        terminal_types={"completed", "cancelled", "failed"},
    )
