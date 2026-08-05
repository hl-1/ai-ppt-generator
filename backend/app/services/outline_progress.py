import json
import uuid

from app.core.redis import get_redis
from app.schemas.outline import OutlineEvent

PROGRESS_TTL_SECONDS = 60 * 60


def outline_channel(project_id: uuid.UUID) -> str:
    return f"outline:{project_id}:events"


def outline_progress_key(project_id: uuid.UUID) -> str:
    return f"outline:{project_id}:progress"


async def publish_outline_event(project_id: uuid.UUID, event: OutlineEvent) -> None:
    redis = get_redis()
    payload = event.model_dump_json()
    # 同时保存最近快照：SSE 断线重连后不必等下一条消息才能恢复当前状态。
    async with redis.pipeline(transaction=True) as pipe:
        pipe.set(outline_progress_key(project_id), payload, ex=PROGRESS_TTL_SECONDS)
        pipe.publish(outline_channel(project_id), payload)
        await pipe.execute()


async def latest_outline_event(project_id: uuid.UUID) -> OutlineEvent | None:
    payload = await get_redis().get(outline_progress_key(project_id))
    if payload is None:
        return None
    return OutlineEvent.model_validate(json.loads(payload))
