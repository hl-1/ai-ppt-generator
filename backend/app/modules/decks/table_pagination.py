"""Persist generated continuation pages and their outlines in one transaction."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.engine.content.content_pagination import split_generated_slide
from app.engine.content.slide_pages import clone_slide_content
from app.engine.layout.generated_layout import fit_generated_slide, title_block
from app.engine.layout.theme import resolve_project_theme
from app.engine.layout.visual_layout import prepare_visual_layout
from app.engine.quality.validation import validate_slide
from app.modules.decks.models import Slide
from app.modules.decks.service import outline_pages, to_content_slide
from app.modules.projects.models import Project
from app.modules.projects.schemas import MAX_DECK_PAGE_COUNT


async def paginate_generated_slides(
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
        if row.status != "ready" or (generated_ids and row.id not in generated_ids):
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
            chunks = split_generated_slide(
                content,
                theme,
                max_parts=MAX_DECK_PAGE_COUNT - projected_count + len(children) + 1,
            )
        except ValueError as error:
            row.issues = [
                *row.issues,
                {
                    "severity": "error",
                    "slide_id": str(row.id),
                    "slot_id": None,
                    "code": "content_pagination",
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
        retained_issues = [
            issue
            for issue in row.issues
            if issue.get("code")
            not in {
                "overflow",
                "capacity",
                "content_pagination",
                "layout_bounds",
                "text_overlap",
                "duplicate_numbering",
            }
        ]
        for part, chunk in enumerate(chunks):
            if part == 0:
                target = row
                target.blocks = [b.model_dump(mode="json") for b in chunk.blocks]
                target.layout_tree = (
                    chunk.layout_tree.model_dump(mode="json") if chunk.layout_tree else None
                )
                target.issues = retained_issues + [
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
                heading = title_block(chunk)
                if heading:
                    chunk = chunk.model_copy(
                        update={
                            "blocks": [
                                block.model_copy(update={"text": outline.title})
                                if block.id == heading.id
                                else block
                                for block in chunk.blocks
                            ]
                        }
                    )
                    chunk = fit_generated_slide(chunk, theme, page_role=page.page_role)
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
                    issues=[{**issue, "slide_id": str(chunk.id)} for issue in retained_issues],
                    revision=1,
                    speaker_notes=row.speaker_notes,
                )
                session.add(target)
                target.issues += [
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


# Compatibility for callers that previously only paginated tables.
paginate_tables = paginate_generated_slides
