import asyncio
import uuid

from app.engine.content.content import BulletsBlock, Slide, TextBlock
from app.engine.layout.flex_layout import FlexContainer, FlexLeaf
from app.infrastructure.database.session import async_session_factory
from app.modules.decks.quality import build_quality_report
from app.modules.decks.service import load_slides
from app.modules.decks.tasks import _finish, _save_ready
from app.modules.projects.models import Project
from tests.test_deck_pages_api import _project_with_pages, _sign_up
from tests.test_deck_pages_api import client as client


def _content(slide_id, *, count=16, indivisible=False):
    items = (
        ["完整保留" * 2000]
        if indivisible
        else [
            f"练习目标{i}：" + "对照岗位要求制定具体任务，完成后记录反馈与下一次改进方向。" * 5
            for i in range(count)
        ]
    )
    return Slide(
        id=str(slide_id),
        layout_id="bullets",
        layout_mode="flex",
        blocks=[
            TextBlock(id="title", slot_id="title", text="完整的练习计划"),
            BulletsBlock(id="body", slot_id="body", items=items),
        ],
        layout_tree=FlexContainer(
            type="column",
            id="root",
            children=[
                FlexLeaf(id="title", block_id="title", text_style="title"),
                FlexLeaf(id="body", block_id="body", text_style="bullet"),
            ],
        ),
    )


def _items(rows):
    return [
        item
        for row in rows
        for block in row.blocks
        if block["type"] == "bullets"
        for item in block["items"]
    ]


async def test_delivery_paginates_before_ready_and_finish_and_retry_preserve_all_text(client):
    headers = await _sign_up(client)
    project, _ = await _project_with_pages(client, headers, ["练习计划"])
    project_id = uuid.UUID(project["id"])
    async with async_session_factory() as session:
        root_id = (await load_slides(session, project_id))[0].id
    content = _content(root_id)
    assert await _save_ready(root_id, content, [], intended_mode="flex")
    async with async_session_factory() as session:
        rows = await load_slides(session, project_id)
        assert len(rows) > 1
        assert all(row.status == "ready" for row in rows)
        assert _items(rows) == content.blocks[1].items
        ids = [row.id for row in rows]
    await _finish(project_id, cancelled=False, generated_ids={root_id})
    async with async_session_factory() as session:
        rows = await load_slides(session, project_id)
        assert [row.id for row in rows] == ids
        assert _items(rows) == content.blocks[1].items
    assert await _save_ready(root_id, content, [], intended_mode="flex")
    async with async_session_factory() as session:
        rows = await load_slides(session, project_id)
        assert len(rows) == len(ids)
        assert _items(rows) == content.blocks[1].items


async def test_unrepairable_delivery_keeps_draft_and_blocks_export(client):
    headers = await _sign_up(client)
    project, _ = await _project_with_pages(client, headers, ["超长单项"])
    project_id = uuid.UUID(project["id"])
    async with async_session_factory() as session:
        root_id = (await load_slides(session, project_id))[0].id
    content = _content(root_id, indivisible=True)
    assert not await _save_ready(root_id, content, [], intended_mode="flex")
    async with async_session_factory() as session:
        record = await session.get(Project, project_id)
        rows = await load_slides(session, project_id)
        assert rows[0].status == "failed"
        assert _items(rows) == content.blocks[1].items
        assert not build_quality_report(record, rows).export_allowed


async def test_concurrent_page_delivery_serializes_outline_changes(client):
    headers = await _sign_up(client)
    project, _ = await _project_with_pages(client, headers, ["练习计划甲", "练习计划乙"])
    project_id = uuid.UUID(project["id"])
    async with async_session_factory() as session:
        roots = [row.id for row in await load_slides(session, project_id)]
    contents = [_content(key, count=12) for key in roots]
    assert all(
        await asyncio.gather(
            *[
                _save_ready(key, content, [], intended_mode="flex")
                for key, content in zip(roots, contents, strict=True)
            ]
        )
    )
    async with async_session_factory() as session:
        record = await session.get(Project, project_id)
        rows = await load_slides(session, project_id)
        assert len(rows) == len(record.outline.pages) == record.page_count
        assert len(set(row.outline_page_id for row in rows)) == len(rows)
        assert [row.position for row in rows] == list(range(1, len(rows) + 1))
        assert _items(rows) == [item for content in contents for item in content.blocks[1].items]
