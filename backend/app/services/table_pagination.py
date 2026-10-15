"""Persist table continuation pages and their outlines in one transaction."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.slide_pages import clone_slide_content
from app.domain.table_pagination import split_table_slide
from app.domain.theme import resolve_project_theme
from app.domain.validation import validate_slide
from app.domain.visual_layout import prepare_visual_layout
from app.models.project import Project
from app.models.slide import Slide
from app.schemas.project import MAX_DECK_PAGE_COUNT
from app.services.deck import outline_pages, to_content_slide


async def paginate_tables(
    session: AsyncSession,
    project: Project,
    slides: list[Slide],
    *,
    generated_ids: set[uuid.UUID] | None = None,
) -> list[Slide]:
    if project.outline is None:
        return slides
    pages = {page.id: page for page in outline_pages(project)}
    theme = resolve_project_theme(project)
    generated_ids = generated_ids or set()
    ordered = []
    new_pages = []
    removed = set()
    changed = False
    projected_count = len(slides)
    for row in slides:
        page = pages.get(row.outline_page_id)
        if page is None or row.id in removed:
            continue
        if page.continuation_of:
            ordered.append(row)
            new_pages.append(page.model_dump(mode="json"))
            continue
        children = [
            s
            for s in slides
            if pages.get(s.outline_page_id) and pages[s.outline_page_id].continuation_of == page.id
        ]
        if children and row.id not in generated_ids:
            ordered.append(row)
            new_pages.append(page.model_dump(mode="json"))
            continue
        if row.status != "ready" or not any(
            b.get("type") in {"table", "financial_table"} for b in row.blocks
        ):
            ordered.append(row)
            new_pages.append(page.model_dump(mode="json"))
            continue
        if any(any(b.get("locked") for b in s.blocks) for s in children):
            row.issues = [
                *row.issues,
                {
                    "severity": "error",
                    "slide_id": str(row.id),
                    "slot_id": None,
                    "code": "table_pagination_locked",
                    "message": "续页包含已锁定内容，无法更新表格分页",
                },
            ]
            ordered.append(row)
            new_pages.append(page.model_dump(mode="json"))
            continue
        content = prepare_visual_layout(to_content_slide(row), theme)
        try:
            chunks = split_table_slide(content)
            if projected_count - len(children) + len(chunks) - 1 > MAX_DECK_PAGE_COUNT:
                raise ValueError("Table pagination exceeds the project page limit")
        except ValueError as error:
            row.issues = [
                *row.issues,
                {
                    "severity": "error",
                    "slide_id": str(row.id),
                    "slot_id": None,
                    "code": "table_pagination",
                    "message": str(error),
                },
            ]
            ordered.append(row)
            new_pages.append(page.model_dump(mode="json"))
            continue
        for child in children:
            await session.delete(child)
            removed.add(child.id)
        if children:
            await session.flush()
        changed = changed or len(chunks) > 1 or bool(children)
        projected_count += len(chunks) - len(children) - 1
        for part, chunk in enumerate(chunks):
            if part == 0:
                target = row
                target.blocks = [b.model_dump(mode="json") for b in chunk.blocks]
                target.issues = [
                    i.model_dump(mode="json") for i in validate_slide(chunk, theme=theme)
                ]
                outline = page
            else:
                outline = page.model_copy(
                    update={
                        "id": uuid.uuid5(page.id, f"table-continuation-{part}"),
                        "title": f"{page.title[:90]} (续 {part + 1})",
                        "continuation_of": page.id,
                    }
                )
                blocks, tree = clone_slide_content(
                    [b.model_dump(mode="json") for b in chunk.blocks],
                    chunk.layout_tree.model_dump(mode="json") if chunk.layout_tree else None,
                )
                target = Slide(
                    id=uuid.uuid4(),
                    project_id=project.id,
                    outline_page_id=outline.id,
                    position=0,
                    layout_id=row.layout_id,
                    layout_mode=row.layout_mode,
                    layout_tree=tree,
                    title=outline.title,
                    status="ready",
                    blocks=blocks,
                    issues=[],
                    revision=1,
                    speaker_notes=row.speaker_notes,
                )
                session.add(target)
                target.issues = [
                    i.model_dump(mode="json")
                    for i in validate_slide(to_content_slide(target), theme=theme)
                ]
            ordered.append(target)
            new_pages.append(outline.model_dump(mode="json"))
    if changed:
        for position, row in enumerate(ordered, start=1):
            row.position = position
        project.outline.pages = new_pages
        project.outline.revision += 1
        project.page_count = len(ordered)
        await session.flush()
    return ordered
