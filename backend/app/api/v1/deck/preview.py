import re
import time
import uuid

from fastapi import APIRouter, HTTPException, Response

from app.api.v1.deck._shared import SessionDep
from app.api.v1.outlines import QueueDep
from app.api.v1.projects import OwnedProject
from app.core.config import get_settings
from app.domain.theme import resolve_project_theme
from app.services.deck import load_slides
from app.services.preview import (
    load_preview_status,
    preview_fingerprint,
    preview_key,
    save_preview_status,
)
from app.services.quality import project_to_content_deck
from app.storage import get_storage

router = APIRouter(prefix="/projects/{project_id}/deck", tags=["deck"])


async def _current(project, session):
    slides = await load_slides(session, project.id)
    if not slides or any(s.status != "ready" for s in slides):
        raise HTTPException(status_code=409, detail="页面尚未全部生成完成")
    deck = project_to_content_deck(project, slides)
    fingerprint = preview_fingerprint(deck, resolve_project_theme(project))
    key = preview_key(project.user_id, project.id, fingerprint)
    return fingerprint, key


@router.get("/preview")
async def get_preview(project: OwnedProject, session: SessionDep) -> dict:
    fingerprint, key = await _current(project, session)
    settings = get_settings()
    if not settings.preview_soffice:
        return {
            "status": "unavailable",
            "fingerprint": fingerprint,
            "page_count": 0,
            "message": "尚未配置实际 PPTX 预览服务",
        }
    return {**load_preview_status(key), "fingerprint": fingerprint}


@router.post("/preview", status_code=202)
async def request_preview(project: OwnedProject, session: SessionDep, queue: QueueDep) -> dict:
    if not get_settings().preview_soffice:
        raise HTTPException(status_code=503, detail="尚未配置实际 PPTX 预览服务")
    fingerprint, key = await _current(project, session)
    current = load_preview_status(key)
    if current["status"] == "ready":
        return {**current, "fingerprint": fingerprint}
    if (
        current["status"] in {"queued", "rendering"}
        and time.time() - current.get("updated_at", 0) < 300
    ):
        return {**current, "fingerprint": fingerprint}
    try:
        save_preview_status(key, "queued")
        job = await queue.enqueue_job(
            "generate_preview",
            str(project.id),
            fingerprint,
            _job_id=f"preview-{project.id}-{fingerprint}-{uuid.uuid4().hex}",
        )
        if job is None:
            raise RuntimeError("预览任务未成功入队")
    except Exception as error:
        save_preview_status(key, "failed", message="预览任务队列暂时不可用")
        raise HTTPException(status_code=503, detail="预览任务队列暂时不可用") from error
    return {"status": "queued", "fingerprint": fingerprint, "page_count": 0}


@router.get("/preview/{fingerprint}/pages/{page_number}")
async def get_preview_page(
    fingerprint: str,
    page_number: int,
    project: OwnedProject,
) -> Response:
    if not re.fullmatch(r"[a-f0-9]{64}", fingerprint) or not 1 <= page_number <= 40:
        raise HTTPException(status_code=404, detail="预览不存在")
    key = preview_key(project.user_id, project.id, fingerprint)
    try:
        data = get_storage().load(f"{key}/{page_number}.png")
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail="预览尚未就绪") from error
    return Response(
        data, media_type="image/png", headers={"Cache-Control": "private, max-age=3600"}
    )
