import uuid

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.redis import get_redis
from app.domain.outline import OutlinePage
from app.models.project import Project
from app.models.slide import Slide
from app.schemas.deck import DeckEvent, DeckPublic, DeckStatus, SlidePublic
from app.services.events import EventStream

deck_events: EventStream[DeckEvent] = EventStream("deck", DeckEvent)

CANCEL_TTL_SECONDS = 60 * 30


def outline_pages(project: Project) -> list[OutlinePage]:
    if project.outline is None:
        return []
    return [OutlinePage.model_validate(page) for page in project.outline.pages]


async def load_slides(session: AsyncSession, project_id: uuid.UUID) -> list[Slide]:
    result = await session.execute(
        select(Slide).where(Slide.project_id == project_id).order_by(Slide.position)
    )
    return list(result.scalars())


async def sync_slides(
    session: AsyncSession,
    project: Project,
    *,
    regenerate_all: bool = False,
) -> list[Slide]:
    """让页面行与已确认的大纲对齐，并返回待生成的页。

    以大纲页 id 为幂等键：重复点生成不会造出重复页，已就绪的页默认保留，
    因此中断后再点一次就是断点续跑。只有布局被改过或用户要求整份重做时，
    才把对应页重置回待生成。
    """
    pages = outline_pages(project)
    existing = {slide.outline_page_id: slide for slide in await load_slides(session, project.id)}
    page_ids = {page.id for page in pages}

    stale = [slide_id for slide_id in existing if slide_id not in page_ids]
    if stale:
        await session.execute(
            delete(Slide).where(Slide.project_id == project.id, Slide.outline_page_id.in_(stale))
        )

    pending: list[Slide] = []
    for position, page in enumerate(pages, start=1):
        slide = existing.get(page.id)
        if slide is None:
            slide = Slide(
                project_id=project.id,
                outline_page_id=page.id,
                position=position,
                layout_id=page.layout_id,
                title=page.title,
                status="pending",
                blocks=[],
                issues=[],
            )
            session.add(slide)
        else:
            slide.position = position
            slide.title = page.title
            if regenerate_all or slide.layout_id != page.layout_id:
                slide.layout_id = page.layout_id
                _reset(slide)

        if slide.status != "ready":
            _reset(slide)
            pending.append(slide)

    await session.flush()
    return pending


def _reset(slide: Slide) -> None:
    slide.status = "pending"
    slide.blocks = []
    slide.issues = []
    slide.error = None


def deck_status(slides: list[Slide]) -> DeckStatus:
    if not slides:
        return "idle"
    if any(slide.status == "generating" for slide in slides):
        return "generating"
    if all(slide.status == "ready" for slide in slides):
        return "ready"
    return "partial"


def to_deck_public(project: Project, slides: list[Slide]) -> DeckPublic:
    return DeckPublic(
        project_id=project.id,
        title=project.title,
        theme_id=project.theme_id,
        status=deck_status(slides),
        total=len(slides),
        ready=sum(1 for slide in slides if slide.status == "ready"),
        failed=sum(1 for slide in slides if slide.status == "failed"),
        slides=[SlidePublic.model_validate(slide) for slide in slides],
    )


def cancel_key(project_id: uuid.UUID) -> str:
    return f"deck:{project_id}:cancel"


async def request_cancel(project_id: uuid.UUID) -> None:
    """取消用 Redis 标记而不是终止任务。

    编排任务在每页开始前检查标记，正在生成的那一页会跑完再停：
    强杀会留下 generating 状态的孤儿行，反而更难恢复。
    """
    await get_redis().set(cancel_key(project_id), "1", ex=CANCEL_TTL_SECONDS)


async def clear_cancel(project_id: uuid.UUID) -> None:
    await get_redis().delete(cancel_key(project_id))


async def is_cancelled(project_id: uuid.UUID) -> bool:
    return await get_redis().exists(cancel_key(project_id)) == 1
