import uuid

import httpx
from fastapi import APIRouter, HTTPException
from redis.exceptions import RedisError

from app.api.v1.deck._shared import QueueDep, SessionDep, _commit_slide_edit, _ensure_editable
from app.api.v1.projects import OwnedProject
from app.domain.flex_edit import build_flex_tree_from_fixed
from app.domain.flex_layout import FlexContainer, FlexLeaf
from app.domain.image_planning import search_queries
from app.domain.layout import get_layout
from app.domain.outline import ImagePlan
from app.images.base import ImageRequest
from app.images.errors import ImageFetchError
from app.images.validate import ImageRejected, validate_image
from app.schemas.deck import SlidePublic
from app.schemas.images import (
    ImageAddRequest,
    ImageApplyRequest,
    ImageGenerateRequest,
    ImageLockRequest,
    ImageSearchPublic,
    ImageSearchRequest,
)
from app.services.image_candidates import load_candidate, search_candidates, stock_provider
from app.services.image_jobs import image_job_active, lock_slide, queue_image_job
from app.services.media import media_url, store_image

router = APIRouter(prefix="/projects/{project_id}/deck", tags=["deck"])


async def _slide(session, project, slide_id):
    slide = await lock_slide(session, project.id, slide_id)
    if slide is None:
        raise HTTPException(404, "页面不存在")
    return slide


def _image(slide, block_id):
    block = next(
        (b for b in slide.blocks if b.get("id") == block_id and b.get("type") == "image"), None
    )
    if block is None:
        raise HTTPException(404, "图片块不存在")
    return block


@router.post("/images/search", response_model=ImageSearchPublic)
async def search_images(body: ImageSearchRequest, project: OwnedProject):
    query = body.query.strip()
    if not query:
        raise HTTPException(422, "请输入检索关键词")
    try:
        return await search_candidates(
            project.id,
            ImageRequest(
                prompt="",
                query=query,
                subject=query,
                queries=search_queries(query),
                aspect_ratio=body.aspect_ratio,
            ),
        )
    except ImageFetchError as error:
        raise HTTPException(503, str(error)) from error
    except RedisError as error:
        raise HTTPException(503, "候选缓存暂时不可用，请重试") from error


@router.post("/slides/{slide_id}/blocks/{block_id}/image/apply", response_model=SlidePublic)
async def apply_image(
    slide_id: uuid.UUID,
    block_id: str,
    body: ImageApplyRequest,
    project: OwnedProject,
    session: SessionDep,
):
    slide = await _slide(session, project, slide_id)
    _ensure_editable(slide, body.revision)
    _image(slide, block_id)
    await session.commit()
    try:
        candidate = await load_candidate(project.id, body.search_id, body.candidate_id)
        async with httpx.AsyncClient(trust_env=False) as client:
            asset = await stock_provider(client).download(candidate)
        extension, _ = validate_image(asset.data)
        key = store_image(
            user_id=project.user_id, project_id=project.id, data=asset.data, extension=extension
        )
    except (ImageFetchError, ImageRejected) as error:
        raise HTTPException(422, str(error)) from error
    except RedisError as error:
        raise HTTPException(503, "候选缓存暂时不可用，请重试") from error
    slide = await _slide(session, project, slide_id)
    _ensure_editable(slide, body.revision)
    target = _image(slide, block_id)
    updated = {
        **target,
        "url": media_url(key),
        "source": "stock",
        "credit": asset.credit,
        "credit_url": asset.credit_url,
        "image_asset_id": asset.asset_id,
        "image_status": "ready",
        "image_error": None,
        "locked": True,
        "image_job_id": None,
        "image_job_started_at": None,
    }
    slide.blocks = [updated if b.get("id") == block_id else b for b in slide.blocks]
    return await _commit_slide_edit(session, project, slide)


@router.post("/slides/{slide_id}/blocks/{block_id}/image/generate", response_model=SlidePublic)
async def generate_image(
    slide_id: uuid.UUID,
    block_id: str,
    body: ImageGenerateRequest,
    project: OwnedProject,
    session: SessionDep,
    queue: QueueDep,
):
    slide = await _slide(session, project, slide_id)
    _ensure_editable(slide, body.revision)
    target = _image(slide, block_id)
    if slide.status != "ready":
        raise HTTPException(409, "请先完成正文生成")
    if target.get("locked"):
        raise HTTPException(409, "图片已锁定，请先解锁")
    if image_job_active(target):
        raise HTTPException(409, "图片正在处理中，请稍后再试")
    previous = target.get("image_plan") or {}
    subject = body.query.strip() or target.get("alt") or slide.title
    require_real = bool(previous.get("require_real")) and body.source != "generated"
    if body.source == "stock":
        require_real = True
    plan = ImagePlan(
        subject=subject[:120],
        queries=search_queries(subject),
        source=body.source,
        require_real=require_real,
    )
    updated = {**target, "image_plan": plan.model_dump(), "alt": plan.subject}
    slide.blocks = [updated if b.get("id") == block_id else b for b in slide.blocks]
    try:
        await queue_image_job(session, queue, slide, [block_id])
    except RedisError as error:
        raise HTTPException(503, "图片任务队列暂时不可用，请重试") from error
    await session.refresh(slide)
    return SlidePublic.model_validate(slide)


@router.patch("/slides/{slide_id}/blocks/{block_id}/image/lock", response_model=SlidePublic)
async def lock_image(
    slide_id: uuid.UUID,
    block_id: str,
    body: ImageLockRequest,
    project: OwnedProject,
    session: SessionDep,
):
    slide = await _slide(session, project, slide_id)
    _ensure_editable(slide, body.revision)
    target = _image(slide, block_id)
    updated = {**target, "locked": body.locked}
    if body.locked:
        updated.update(
            image_job_id=None,
            image_job_started_at=None,
            image_status="ready" if target.get("url") else "idle",
            image_error=None,
        )
    slide.blocks = [updated if b.get("id") == block_id else b for b in slide.blocks]
    return await _commit_slide_edit(session, project, slide)


@router.post("/slides/{slide_id}/images", response_model=SlidePublic)
async def add_image(
    slide_id: uuid.UUID, body: ImageAddRequest, project: OwnedProject, session: SessionDep
):
    slide = await _slide(session, project, slide_id)
    _ensure_editable(slide, body.revision)
    if len([b for b in slide.blocks if b.get("type") == "image"]) >= 3:
        raise HTTPException(422, "每页最多添加三张图片")
    tree = (
        FlexContainer.model_validate(slide.layout_tree)
        if slide.layout_tree
        else (build_flex_tree_from_fixed(get_layout(slide.layout_id), slide.blocks))
    )
    block_id = uuid.uuid4().hex[:12]
    tree = FlexContainer(
        type="row",
        id=f"image-row-{block_id}",
        ratios=[0.6, 0.4],
        children=[tree, FlexLeaf(id=f"leaf-{block_id}", block_id=block_id)],
    )
    slide.layout_mode = "flex"
    slide.layout_tree = tree.model_dump(mode="json")
    slide.blocks = [
        *slide.blocks,
        {
            "id": block_id,
            "slot_id": "visual",
            "type": "image",
            "alt": body.subject,
            "source": "placeholder",
            "locked": False,
        },
    ]
    return await _commit_slide_edit(session, project, slide)
