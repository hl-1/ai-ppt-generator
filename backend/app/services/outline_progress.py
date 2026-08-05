import uuid

from app.schemas.outline import OutlineEvent
from app.services.events import EventStream

outline_events: EventStream[OutlineEvent] = EventStream("outline", OutlineEvent)


def outline_channel(project_id: uuid.UUID) -> str:
    return outline_events.channel(project_id)


async def publish_outline_event(project_id: uuid.UUID, event: OutlineEvent) -> None:
    await outline_events.publish(project_id, event)


async def latest_outline_event(project_id: uuid.UUID) -> OutlineEvent | None:
    return await outline_events.latest(project_id)
