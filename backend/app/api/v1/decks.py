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
from app.domain.layout import get_layout
from app.domain.layout_switch import (
    LayoutSwitchOk,
    list_layout_candidates,
    plan_layout_switch,
)
from app.domain.slide_patch import (
    apply_patches,
    content_snapshot,
    filter_patches,
    unlocked_editable_blocks,
)
from app.images.validate import ImageRejected, validate_image
from app.llm.base import SlideEditInput
from app.llm.errors import InvalidSlideEditOutputError, LLMNotConfiguredError
from app.llm.slide_edit import block_to_edit_input
from app.models.project import Project
from app.models.slide import Slide
from app.schemas.deck import (
    AiEditApplyRequest,
    AiEditOperationPublic,
    AiEditProposalPublic,
    AiEditRequest,
    BlockUpdate,
    DeckEvent,
    DeckGenerateAccepted,
    DeckGenerateRequest,
    DeckPublic,
    DiscardedOperationPublic,
    LayoutCandidatePublic,
    LayoutSwitchRequest,
    SlideOrderRequest,
    SlidePublic,
)
from app.services.deck import (
    clear_cancel,
    deck_events,
    deck_status,
    load_slides,
    refresh_slide_issues,
    request_cancel,
    sync_slides,
    to_deck_public,
)
from app.services.media import media_url, store_image
from app.worker.context import create_slide_edit_generator
from app.workflows.slide_edit import (
    build_slide_edit_workflow,
    parse_slide_blocks,
    run_slide_edit_workflow,
)

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


def _find_slide(slides: list[Slide], slide_id: uuid.UUID) -> Slide:
    slide = next((item for item in slides if item.id == slide_id), None)
    if slide is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="页面不存在")
    return slide


def _ensure_editable(slide: Slide, revision: int) -> None:
    # 页面生成完成时会整块覆盖 blocks，此时编辑会被无声冲掉
    if slide.status == "generating":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="页面正在生成中，请稍后再编辑",
        )
    if slide.revision != revision:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="页面已被其他操作更新，请刷新后重试",
        )


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


@router.patch(
    "/slides/{slide_id}/blocks/{block_id}",
    response_model=SlidePublic,
)
async def update_slide_block(
    slide_id: uuid.UUID,
    block_id: str,
    body: BlockUpdate,
    project: OwnedProject,
    session: SessionDep,
) -> SlidePublic:
    slides = await load_slides(session, project.id)
    slide = _find_slide(slides, slide_id)
    target = next((block for block in slide.blocks if block.get("id") == block_id), None)
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="内容块不存在")

    _ensure_editable(slide, body.revision)

    # 请求体按 type 判别；与存量块类型不符说明前端状态已过期
    if target.get("type") != body.type:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"块类型不匹配，当前为 {target.get('type')}，不能按 {body.type} 保存",
        )

    updated = {**target, "locked": True}
    if body.type == "text":
        updated["text"] = body.text
    elif body.type == "bullets":
        updated["items"] = body.items
    elif body.type == "kpi":
        updated["value"] = body.value
        updated["label"] = body.label
        updated["note"] = body.note
    else:
        updated["header"] = body.header
        updated["rows"] = body.rows

    slide.blocks = [updated if block.get("id") == block_id else block for block in slide.blocks]
    refresh_slide_issues(slide)
    slide.revision += 1
    await session.commit()
    await session.refresh(slide)
    return SlidePublic.model_validate(slide)


@router.put("/slides/order", response_model=list[SlidePublic])
async def reorder_slides(
    body: SlideOrderRequest,
    project: OwnedProject,
    session: SessionDep,
) -> list[SlidePublic]:
    slides = await load_slides(session, project.id)
    if any(slide.status == "generating" for slide in slides):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="页面正在生成中，请稍后再调整顺序",
        )

    current_ids = {slide.id for slide in slides}
    requested = body.slide_ids
    if len(requested) != len(set(requested)) or set(requested) != current_ids:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="页面列表已变化，请刷新后重试",
        )

    by_id = {slide.id: slide for slide in slides}
    # position 无唯一约束，可直接按目标下标重写
    for position, slide_id in enumerate(requested, start=1):
        slide = by_id[slide_id]
        slide.position = position
        slide.revision += 1

    await session.commit()
    ordered = await load_slides(session, project.id)
    return [SlidePublic.model_validate(slide) for slide in ordered]


@router.get(
    "/slides/{slide_id}/layouts",
    response_model=list[LayoutCandidatePublic],
)
async def list_slide_layouts(
    slide_id: uuid.UUID,
    project: OwnedProject,
    session: SessionDep,
) -> list[LayoutCandidatePublic]:
    slides = await load_slides(session, project.id)
    slide = _find_slide(slides, slide_id)
    return [
        LayoutCandidatePublic(
            layout_id=item.layout_id,
            name=item.name,
            usage=item.usage,
            compatible=item.compatible,
            reason=item.reason,
            current=item.current,
        )
        for item in list_layout_candidates(slide.blocks, slide.layout_id)
    ]


@router.put("/slides/{slide_id}/layout", response_model=SlidePublic)
async def switch_slide_layout(
    slide_id: uuid.UUID,
    body: LayoutSwitchRequest,
    project: OwnedProject,
    session: SessionDep,
) -> SlidePublic:
    slides = await load_slides(session, project.id)
    slide = _find_slide(slides, slide_id)
    _ensure_editable(slide, body.revision)

    try:
        get_layout(body.layout_id)
    except KeyError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="布局不存在",
        ) from error

    result = plan_layout_switch(slide.blocks, slide.layout_id, body.layout_id)
    if not isinstance(result, LayoutSwitchOk):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=result.reason)

    # 只改槽位归属，不改块内容与 locked
    slide.blocks = [{**block, "slot_id": result.mapping[block["id"]]} for block in slide.blocks]
    slide.layout_id = body.layout_id
    refresh_slide_issues(slide)
    slide.revision += 1
    await session.commit()
    await session.refresh(slide)
    return SlidePublic.model_validate(slide)


@router.post(
    "/slides/{slide_id}/ai-edit",
    response_model=AiEditProposalPublic,
)
async def propose_slide_ai_edit(
    slide_id: uuid.UUID,
    body: AiEditRequest,
    project: OwnedProject,
    session: SessionDep,
) -> AiEditProposalPublic:
    slides = await load_slides(session, project.id)
    slide = _find_slide(slides, slide_id)
    _ensure_editable(slide, body.revision)

    blocks = parse_slide_blocks(slide.blocks)
    editable = unlocked_editable_blocks(blocks)
    if not editable:
        return AiEditProposalPublic(
            revision=slide.revision,
            operations=[],
            discarded=[],
            warnings=[],
        )

    instruction = body.instruction.strip() if body.instruction else None
    payload = SlideEditInput(
        deck_title=project.title,
        audience=project.audience,
        tone=project.tone,
        page_title=slide.title,
        layout_id=slide.layout_id,
        action=body.action,
        instruction=instruction or None,
        blocks=[block_to_edit_input(block) for block in editable],
    )

    workflow = build_slide_edit_workflow(create_slide_edit_generator())
    try:
        operations, discarded, issues, _patched = await run_slide_edit_workflow(
            workflow,
            payload=payload,
            slide_id=str(slide.id),
            layout_id=slide.layout_id,
            blocks=blocks,
        )
    except LLMNotConfiguredError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(error),
        ) from error
    except InvalidSlideEditOutputError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(error),
        ) from error

    by_id = {block.id: block for block in blocks}
    preview: list[AiEditOperationPublic] = []
    for op in operations:
        block = by_id[op.block_id]
        preview.append(
            AiEditOperationPublic(
                block_id=op.block_id,
                slot_id=block.slot_id,
                type=op.type,
                before=content_snapshot(block),
                after=op,
            )
        )

    return AiEditProposalPublic(
        revision=slide.revision,
        operations=preview,
        discarded=[
            DiscardedOperationPublic(block_id=item.block_id, reason=item.reason)
            for item in discarded
        ],
        warnings=[issue for issue in issues if issue.severity == "warning"],
    )


@router.post(
    "/slides/{slide_id}/ai-edit/apply",
    response_model=SlidePublic,
)
async def apply_slide_ai_edit(
    slide_id: uuid.UUID,
    body: AiEditApplyRequest,
    project: OwnedProject,
    session: SessionDep,
) -> SlidePublic:
    slides = await load_slides(session, project.id)
    slide = _find_slide(slides, slide_id)
    _ensure_editable(slide, body.revision)

    blocks = parse_slide_blocks(slide.blocks)
    filtered = filter_patches(blocks, list(body.operations))
    patched = apply_patches(blocks, filtered.accepted)
    # AI 改过的块不置 locked：locked 表示「人工修改过」；若 AI 也置位，
    # 一页被 AI 改过后就再也改不动了。
    slide.blocks = [block.model_dump(mode="json") for block in patched]
    refresh_slide_issues(slide)
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
