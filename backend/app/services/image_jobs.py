import time
import uuid

from redis.exceptions import RedisError
from sqlalchemy import select

from app.models.slide import Slide


async def lock_slide(session, project_id: uuid.UUID, slide_id: uuid.UUID) -> Slide | None:
    result = await session.execute(
        select(Slide)
        .where(Slide.id == slide_id, Slide.project_id == project_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    return result.scalar_one_or_none()


async def queue_image_job(session, queue, slide: Slide, block_ids: list[str]) -> str:
    job_id = f"images-{uuid.uuid4().hex}"
    slide.blocks = [
        {
            **block,
            "image_job_id": job_id,
            "image_status": "queued",
            "image_error": None,
            "image_job_started_at": time.time(),
        }
        if block.get("id") in block_ids and not block.get("locked")
        else block
        for block in slide.blocks
    ]
    slide.revision += 1
    revision = slide.revision
    await session.commit()
    try:
        job = await queue.enqueue_job(
            "generate_slide_images",
            str(slide.project_id),
            str(slide.id),
            job_id,
            revision,
            _job_id=job_id,
        )
        if job is None:
            raise RedisError("Image job was not accepted")
    except RedisError:
        current = await lock_slide(session, slide.project_id, slide.id)
        if current:
            current.blocks = [
                {
                    **block,
                    "image_job_id": None,
                    "image_job_started_at": None,
                    "image_status": "failed",
                    "image_error": "图片任务入队失败，请重试",
                }
                if block.get("image_job_id") == job_id
                else block
                for block in current.blocks
            ]
            current.revision += 1
            await session.commit()
        raise
    return job_id


def image_job_active(block: dict) -> bool:
    started = block.get("image_job_started_at") or 0
    return block.get("image_status") == "queued" and time.time() - started < 15 * 60
