from __future__ import annotations

import asyncio
import logging
import uuid

from sqlalchemy import select

from app.core.config import get_settings
from app.engine.layout.theme import resolve_project_theme
from app.engine.pptx.pptx import render_deck_to_pptx
from app.engine.pptx.preview import render_pptx_preview
from app.engine.pptx.verify import verify_pptx
from app.infrastructure.database.session import async_session_factory
from app.infrastructure.storage import get_storage
from app.modules.decks.preview import preview_fingerprint, preview_key, save_preview_status
from app.modules.decks.quality import project_to_content_deck
from app.modules.decks.service import load_slides
from app.modules.projects.models import Project

logger = logging.getLogger(__name__)


async def generate_preview(ctx: dict, project_id: str, fingerprint: str) -> None:
    async with async_session_factory() as session:
        project = await session.scalar(select(Project).where(Project.id == uuid.UUID(project_id)))
        if project is None:
            return
        slides = await load_slides(session, project.id)
        deck = project_to_content_deck(project, slides)
        theme = resolve_project_theme(project)
        key = preview_key(project.user_id, project.id, fingerprint)
        if preview_fingerprint(deck, theme) != fingerprint:
            save_preview_status(key, "failed", message="内容已变化，请重新生成预览")
            return
    settings = get_settings()
    save_preview_status(key, "rendering")
    try:

        def render():
            data = render_deck_to_pptx(deck, theme=theme).getvalue()
            report = verify_pptx(data, deck)
            if not report.passed:
                raise ValueError("PPTX 回读检查未通过")
            pages = render_pptx_preview(
                data,
                soffice=settings.preview_soffice,
                pdftoppm=settings.preview_pdftoppm,
                expected_pages=len(deck.slides),
            )
            storage = get_storage()
            storage.save(f"{key}/deck.pptx", data)
            for index, page in enumerate(pages, 1):
                storage.save(f"{key}/{index}.png", page)
            save_preview_status(key, "ready", page_count=len(pages))

        await asyncio.to_thread(render)
    except Exception:
        logger.exception("PPTX preview failed for %s", project_id)
        save_preview_status(key, "failed", message="实际预览生成失败，请检查渲染服务后重试")
