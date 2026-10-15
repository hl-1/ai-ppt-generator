"""Summarize loaded image references independently of page generation status."""

from __future__ import annotations

import time
from collections.abc import Mapping, Sequence
from typing import Any

from pydantic import BaseModel


class ImageCoverage(BaseModel):
    minimum: int = 0
    planned: int = 0
    ready: int = 0
    pending: int = 0
    failed: int = 0
    missing: int = 0
    duplicates: int = 0


def summarize_images(
    blocks: Sequence[Mapping[str, Any]], *, minimum: int = 0, unfilled_plans: int = 0
) -> ImageCoverage:
    result = ImageCoverage(minimum=minimum, missing=unfilled_plans, planned=unfilled_plans)
    seen: set[str] = set()
    for block in blocks:
        if block.get("type") != "image":
            continue
        result.planned += 1
        queued = block.get("image_status") == "queued" and (
            time.time() - (block.get("image_job_started_at") or 0) < 15 * 60
        )
        if queued:
            result.pending += 1
        elif block.get("image_status") in {"failed", "queued"}:
            result.failed += 1
        if block.get("url") and block.get("source") != "placeholder":
            identities = {f"url:{block['url']}"}
            if block.get("image_asset_id"):
                identities.add(f"asset:{block['image_asset_id']}")
            if identities & seen:
                result.duplicates += 1
            else:
                result.ready += 1
            seen.update(identities)
        elif not queued and block.get("image_status") not in {"failed", "queued"}:
            result.missing += 1
    return result
