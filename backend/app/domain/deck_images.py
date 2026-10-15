"""Plan image coverage across a deck before pages are generated concurrently."""

from __future__ import annotations

import math
import re

from app.domain.image_planning import plan_page_image, search_queries
from app.domain.outline import ImagePlan, OutlinePageDraft

_VISUAL_TOPICS = ("旅游", "旅行", "景点", "产品介绍", "产品发布", "travel", "product")
_IMAGE_TOPICS = ("场景", "案例", "应用", "体验", "外观", "设备", "人物", "建筑", "景点")
_DENSE_TOPICS = ("接口", "字段", "数据库", "明细", "预算", "参数", "财务", "权限")
_STRUCTURED_KINDS = {
    "trend", "chart", "comparison", "composition", "flow", "timeline", "kpi",
    "waterfall", "actions",
}


def image_budget(page_count: int, *, scenario: str = "general", title: str = "") -> tuple[int, int]:
    page_count = max(0, page_count)
    minimum = min(2, page_count)
    visual = scenario == "travel_plan" or any(word in title.lower() for word in _VISUAL_TOPICS)
    ratio = 0.45 if visual else 0.25 if scenario == "business_review" else 0.3
    lower, upper = (2, 3) if page_count <= 8 else (3, 5) if page_count <= 15 else (5, 8)
    target = min(page_count, max(lower, min(upper, math.ceil(page_count * ratio))))
    return minimum, target


def _candidate_score(page: OutlinePageDraft) -> int | None:
    if page.page_role in {"toc", "section"} or page.travel_page:
        return None
    if page.visual_type not in {"auto", "photo", "illustration"}:
        return None
    if page.evidence_kind in _STRUCTURED_KINDS:
        return None
    if any(item.value for item in page.evidence):
        return None
    if page.evidence_kind == "table":
        return None
    text = " ".join([page.title, page.objective])
    if any(word in text for word in _DENSE_TOPICS):
        return None
    if page.page_role == "cover":
        return 100
    if any(word in text for word in _IMAGE_TOPICS):
        return 80
    if page.narrative_role in {"executive_summary", "summary", "decision"}:
        return 10
    return 40


def _subject(page: OutlinePageDraft, deck_title: str) -> str:
    if page.visual:
        return page.visual[:120]
    title = re.sub(r"^(?:第\s*\d+\s*[页章节]|\d+[.、])\s*", "", page.title).strip()
    context = page.objective if page.page_role == "cover" else page.key_points[0]
    return f"{deck_title}：{title}；{context}"[:120]


def plan_deck_images(
    pages: list[OutlinePageDraft], *, deck_title: str, scenario: str = "general"
) -> list[OutlinePageDraft]:
    """Preserve evidence pages and fill missing image plans on qualitative pages."""
    result = [plan_page_image(page, deck_title=deck_title) for page in pages]
    _, target = image_budget(len(pages), scenario=scenario, title=deck_title)
    used = {
        re.sub(r"\s+", "", page.image_plan.subject).casefold()
        for page in result if page.image_plan
    }
    selected = [index for index, page in enumerate(result) if page.image_plan]
    candidates = {
        index: score
        for index, page in enumerate(result)
        if not page.image_plan and (score := _candidate_score(page)) is not None
    }
    while len(used) < target and candidates:
        index = max(candidates, key=lambda value: (
            candidates[value],
            min((abs(value - other) for other in selected), default=len(pages)),
            -value,
        ))
        candidates.pop(index)
        page = result[index]
        subject = _subject(page, deck_title)
        identity = re.sub(r"\s+", "", subject).casefold()
        if identity in used:
            continue
        # Keep concrete model-supplied descriptions; a fallback is an explicit concept illustration.
        plan = ImagePlan(
            subject=subject,
            queries=search_queries(subject),
            source="auto" if page.visual else "generated",
            purpose="cover" if page.page_role == "cover" else "subject",
        )
        result[index] = plan_page_image(
            page.model_copy(update={
                "visual_type": "auto" if page.visual else "illustration",
                "image_plan": plan,
            }),
            deck_title=deck_title,
        )
        used.add(identity)
        selected.append(index)
    minimum, _ = image_budget(len(pages), scenario=scenario, title=deck_title)
    if len(used) < minimum and result:
        note = "适合配图的页面不足两页，请补充场景、案例或产品素材；保留现有数据和结构表达"
        result[0] = result[0].model_copy(update={
            "planning_notes": list(dict.fromkeys([*result[0].planning_notes, note]))[:16],
        })
    return result
