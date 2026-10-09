import asyncio
import logging
import uuid

import httpx

from app.core.config import get_settings
from app.core.db import async_session_factory
from app.core.redis import get_redis
from app.images.pipeline import create_image_pipeline
from app.models.project import Project
from app.services.deck import load_slides, to_content_slide
from app.services.image_jobs import lock_slide
from app.services.slide_images import resolve_slide_images

logger = logging.getLogger(__name__)


async def generate_slide_images(
    ctx, project_id: str, slide_id: str, job_id: str, revision: int
) -> None:
    project_uuid, slide_uuid = uuid.UUID(project_id), uuid.UUID(slide_id)
    async with async_session_factory() as session:
        slide = await lock_slide(session, project_uuid, slide_uuid)
        project = await session.get(Project, project_uuid)
        if slide is None or project is None:
            return
        targets = {
            b["id"] for b in slide.blocks if b.get("image_job_id") == job_id and not b.get("locked")
        }
        if not targets:
            return
        if slide.revision != revision or slide.status != "ready":
            await _save_result(
                project_uuid,
                slide_uuid,
                job_id,
                revision,
                None,
                "页面已修改，请重新尝试配图",
                session=session,
            )
            return
        content = to_content_slide(slide)
        originals = {b.id: b for b in content.blocks}
        content = content.model_copy(
            update={
                "blocks": [
                    b.model_copy(update={"url": None})
                    if b.id in targets
                    else b.model_copy(update={"locked": True})
                    if b.type == "image"
                    else b
                    for b in content.blocks
                ]
            }
        )
        used = {
            b.get("image_asset_id")
            for other in await load_slides(session, project_uuid)
            for b in other.blocks
            if b.get("image_asset_id")
        }
        user_id, title, page_title = project.user_id, project.title, slide.title
        await session.commit()

    async def reserve(asset_id: str) -> bool:
        return bool(
            await get_redis().set(
                f"image-reservation:{project_id}:{asset_id}", job_id, nx=True, ex=6 * 60 * 60
            )
        )

    try:
        async with asyncio.timeout(get_settings().image_timeout_seconds * len(targets) + 30):
            async with httpx.AsyncClient(trust_env=False) as client:
                pipeline = ctx.get("image_pipeline") or create_image_pipeline(
                    client, reserve=reserve
                )
                resolved = await resolve_slide_images(
                    pipeline,
                    user_id=user_id,
                    project_id=project_uuid,
                    deck_title=title,
                    page_title=page_title,
                    slide=content,
                    excluded_ids=used,
                )
        updates = {}
        for block in resolved.blocks:
            if block.id not in targets:
                continue
            if block.image_status == "failed" and originals[block.id].url:
                block = block.model_copy(update={"url": originals[block.id].url})
            updates[block.id] = block.model_dump(mode="json")
        await _save_result(project_uuid, slide_uuid, job_id, revision, updates, None)
    except asyncio.CancelledError:
        await _save_result(
            project_uuid, slide_uuid, job_id, revision, None, "图片任务已中断，请重试"
        )
        raise
    except Exception as error:
        logger.warning("image task failed job=%s type=%s", job_id, type(error).__name__)
        await _save_result(
            project_uuid, slide_uuid, job_id, revision, None, "图片处理超时或失败，请重试"
        )


async def _save_result(project_id, slide_id, job_id, revision, updates, error, *, session=None):
    if session is None:
        async with async_session_factory() as owned:
            return await _save_result(
                project_id, slide_id, job_id, revision, updates, error, session=owned
            )
    slide = await lock_slide(session, project_id, slide_id)
    if slide is None:
        return
    stale = slide.revision != revision or slide.status != "ready"
    changed = False
    blocks = []
    for block in slide.blocks:
        if block.get("image_job_id") != job_id or block.get("locked"):
            blocks.append(block)
            continue
        changed = True
        if stale or error or not updates or block["id"] not in updates:
            updated = {
                **block,
                "image_status": "failed",
                "image_error": "页面已修改，请重新尝试配图" if stale else error,
            }
        else:
            updated = updates[block["id"]]
        blocks.append({**updated, "image_job_id": None, "image_job_started_at": None})
    if changed:
        slide.blocks = blocks
        slide.revision += 1
        await session.commit()
