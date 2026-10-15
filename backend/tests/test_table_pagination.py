import uuid

from app.core.db import async_session_factory
from app.domain.content import TableBlock
from app.domain.flex_layout import FlexContainer, FlexLeaf
from app.models.project import Project
from app.services.deck import load_slides, sync_slides
from app.services.table_pagination import paginate_tables
from tests.test_deck_pages_api import _project_with_pages, _sign_up
from tests.test_deck_pages_api import client as client


async def test_pagination_persists_order_outline_and_rows_and_is_retryable(client):
    headers = await _sign_up(client)
    project, _ = await _project_with_pages(client, headers, ["数据表"])
    full = TableBlock(
        id="schema",
        slot_id="schema",
        header=["标识符", "完整说明"],
        rows=[[f"music_recommendation_runs_{i}", "完整数据和约束" * 12] for i in range(24)],
    )
    tree = FlexContainer(
        id="root", type="column", children=[FlexLeaf(id="table", block_id="schema")]
    )
    async with async_session_factory() as session:
        record = await session.get(Project, uuid.UUID(project["id"]))
        rows = await load_slides(session, record.id)
        root = rows[0]
        root.blocks = [full.model_dump(mode="json")]
        root.layout_tree = tree.model_dump(mode="json")
        ordered = await paginate_tables(session, record, rows)
        await session.commit()
        assert len(ordered) > 1
        assert record.page_count == len(record.outline.pages) == len(ordered)
        assert [s.position for s in ordered] == list(range(1, len(ordered) + 1))
        assert [row for s in ordered for row in s.blocks[0]["rows"]] == full.rows
        original_ids = [s.id for s in ordered]
        again = await paginate_tables(session, record, ordered)
        await session.commit()
        assert [s.id for s in again] == original_ids
        assert await sync_slides(session, record) == []
        root.blocks = [full.model_dump(mode="json")]
        root.revision += 1
        regenerated = await paginate_tables(session, record, again, generated_ids={root.id})
        await session.commit()
        assert len(regenerated) == len(ordered)
        assert [row for s in regenerated for row in s.blocks[0]["rows"]] == full.rows
        assert len(set(s.outline_page_id for s in regenerated)) == len(regenerated)
