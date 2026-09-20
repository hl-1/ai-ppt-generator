from __future__ import annotations

import hashlib
import json
import time

from app.domain.content import Deck
from app.domain.theme import Theme
from app.storage import get_storage


def preview_fingerprint(deck: Deck, theme: Theme) -> str:
    payload = json.dumps(
        {"version": 1, "deck": deck.model_dump(mode="json"), "theme": theme.model_dump()},
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def preview_key(user_id, project_id, fingerprint: str) -> str:
    return f"previews/{user_id}/{project_id}/{fingerprint}"


def load_preview_status(key: str) -> dict:
    try:
        current = json.loads(get_storage().load(f"{key}/status.json"))
        if current.get("status") in {"queued", "rendering"} and (
            time.time() - current.get("updated_at", 0) >= 300
        ):
            return {"status": "failed", "page_count": 0, "message": "预览任务超时，请重试"}
        return current
    except FileNotFoundError:
        return {"status": "missing", "page_count": 0}


def save_preview_status(key: str, status: str, **fields) -> None:
    get_storage().save(
        f"{key}/status.json",
        json.dumps(
            {"status": status, "page_count": 0, "updated_at": time.time(), **fields},
            ensure_ascii=False,
        ).encode(),
    )
