"""Image intent is planned before concurrent page generation."""

from __future__ import annotations

from app.domain.outline import ImagePlan, OutlinePageDraft

IMAGE_VISUAL_TYPES = {"photo", "illustration"}
LANDMARKS = {
    "故宫": ("Beijing Forbidden City", "forbidden city", "palace museum"),
    "天坛": ("Beijing Temple of Heaven", "temple of heaven", "tiantan"),
    "长城": ("Beijing Great Wall", "great wall", "badaling", "mutianyu"),
    "颐和园": ("Beijing Summer Palace", "summer palace"),
    "天安门": ("Beijing Tiananmen", "tiananmen"),
    "胡同": ("Beijing hutong", "hutong"),
    "鸟巢": ("Beijing National Stadium", "national stadium", "bird's nest"),
}


def search_queries(subject: str, queries: list[str] | None = None) -> list[str]:
    preferred = [values[0] for name, values in LANDMARKS.items() if name in subject]
    if not preferred and "北京" in subject:
        preferred = ["Beijing city architecture"]
    return list(
        dict.fromkeys(q.strip()[:120] for q in [*(queries or []), *preferred, subject] if q.strip())
    )[:4]


def subject_terms(subject: str, queries: list[str]) -> list[str]:
    for name, aliases in LANDMARKS.items():
        if name in subject or any(alias in subject.lower() for alias in aliases):
            return list(aliases[1:])
    if "北京" in subject:
        return ["beijing"]
    terms = [subject.lower(), *(query.lower() for query in queries)]
    return list(dict.fromkeys(term for term in terms if term.strip()))


def plan_page_image(page: OutlinePageDraft, *, deck_title: str = "") -> OutlinePageDraft:
    explicit = page.visual_type in IMAGE_VISUAL_TYPES
    plan = page.image_plan
    if not explicit and page.visual_type != "auto":
        return page.model_copy(update={"visual": None, "image_plan": None})
    subject = plan.subject if plan else page.visual
    context = " ".join([deck_title, page.title, page.objective])
    travel = any(word in context for word in ("旅游", "旅行", "景点", "游览", "travel"))
    if not subject and (explicit or (travel and page.page_role == "cover")):
        subject = page.title[:120]
    if not subject and travel and page.page_role == "content":
        subject = next((name for name in LANDMARKS if name in page.title), None)
    if not subject:
        return page
    if not explicit and page.evidence_kind != "narrative":
        return page.model_copy(update={"visual": None, "image_plan": None})
    real = page.visual_type != "illustration" and (
        page.visual_type == "photo" or (plan.require_real if plan else travel)
    )
    source = (
        "stock"
        if real
        else "generated"
        if page.visual_type == "illustration"
        else (plan.source if plan else "auto")
    )
    plan = ImagePlan(
        subject=subject[:120],
        queries=search_queries(subject, plan.queries if plan else None),
        source=source,
        require_real=real,
        purpose="cover" if page.page_role == "cover" else (plan.purpose if plan else "subject"),
    )
    return page.model_copy(
        update={
            "visual": plan.subject,
            "image_plan": plan,
            "visual_type": "photo" if real else page.visual_type,
            "evidence_kind": "narrative" if explicit else page.evidence_kind,
            "layout_id": "image-right"
            if page.layout_id in {"cover", "bullets", "chart", "kpi"}
            else page.layout_id,
        }
    )


def bind_page_image(slide, page: OutlinePageDraft):
    from app.domain.content import ImageBlock

    if page.image_plan is None:
        return slide
    images = [block for block in slide.blocks if block.type == "image"]
    if images:
        blocks = [
            block.model_copy(update={"alt": page.image_plan.subject, "image_plan": page.image_plan})
            if block.type == "image" and not block.locked
            else block
            for block in slide.blocks
        ]
    else:
        block_id = "planned-image"
        while any(block.id == block_id for block in slide.blocks):
            block_id += "-1"
        blocks = [
            *slide.blocks,
            ImageBlock(
                id=block_id,
                slot_id="image" if slide.layout_mode == "fixed" else "visual",
                alt=page.image_plan.subject,
                source="placeholder",
                image_plan=page.image_plan,
            ),
        ]
    return slide.model_copy(update={"blocks": blocks})
