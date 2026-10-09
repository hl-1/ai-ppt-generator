"""Topic-mode uniqueness checks for outlines and rendered slide layouts."""

from __future__ import annotations

import re
from difflib import SequenceMatcher

from app.domain.content import Slide
from app.domain.flex_layout import FlexLeaf, FlexNode
from app.domain.outline import OutlinePageDraft
from app.domain.page_rhythm import TOPIC_LAYOUT_CAPACITY


def find_duplicate_topic_layouts(slides: list[Slide]) -> list[tuple[str, str]]:
    """Return flex slide pairs that render with the same structural layout."""
    if len(slides) > TOPIC_LAYOUT_CAPACITY:
        return []

    seen: dict[str, str] = {}
    duplicates: list[tuple[str, str]] = []
    for slide in slides:
        if slide.layout_mode != "flex" or slide.layout_tree is None:
            continue
        signature = _layout_signature(slide)
        previous = seen.get(signature)
        if previous is not None:
            duplicates.append((previous, slide.id))
        else:
            seen[signature] = slide.id
    return duplicates


def _layout_signature(slide: Slide) -> str:
    block_roles = {block.id: _layout_block_role(block.type) for block in slide.blocks}

    def visit(node: FlexNode):
        if isinstance(node, FlexLeaf):
            return ("block", block_roles.get(node.block_id, "content"), node.bleed)
        ratios = tuple(round(value) for value in node.ratios or ())
        return (
            node.type,
            ratios,
            node.preset,
            tuple(visit(child) for child in node.children),
        )

    return repr(visit(slide.layout_tree))


def _layout_block_role(block_type: str) -> str:
    if block_type in {"chart", "diagram", "image", "financial_table", "waterfall", "combo_chart"}:
        return "visual"
    if block_type == "kpi":
        return "metric"
    if block_type == "callout":
        return "note"
    return "content"


def find_duplicate_topic_pages(
    pages: list[OutlinePageDraft], *, travel_mode: bool = False
) -> list[str]:
    duplicates: list[str] = []
    eligible = [
        (index, page)
        for index, page in enumerate(pages, start=1)
        if page.page_role not in {"cover", "toc"}
    ]
    for offset, (left_index, left) in enumerate(eligible):
        for right_index, right in eligible[offset + 1 :]:
            reason = _duplicate_reason(left, right, travel_mode=travel_mode)
            if reason:
                duplicates.append(
                    f"第 {left_index} 页「{left.title}」与"
                    f"第 {right_index} 页「{right.title}」{reason}；"
                    "请改为不同的问题、结论和支撑要点，不要只更换标题或视觉类型。"
                )
    return duplicates


def _itinerary_scope(page: OutlinePageDraft) -> set[str]:
    title = re.fullmatch(r"第\s*(\d+)(?:\s*[-–至]\s*(\d+))?\s*天行程", page.title)
    if title is None:
        return set()
    first = int(title[1])
    last = int(title[2] or title[1])
    days: set[int] = set()
    scope: set[str] = set()
    for point in page.key_points:
        match = re.match(r"第\s*(\d+)\s*天[（(]([^）)]+)[）)]\s*建议路线[：:]", point)
        if match is None:
            continue
        day = int(match[1])
        days.add(day)
        date = match[2].strip()
        scope.add(date if re.fullmatch(r"\d{4}-\d{2}-\d{2}", date) else f"day:{day}")
    # A renamed copy must not gain a new scope from its title alone.
    if days and min(days) == first and max(days) == last and len(days) == last - first + 1:
        return scope
    return set()


def _duplicate_reason(
    left: OutlinePageDraft, right: OutlinePageDraft, *, travel_mode: bool = False
) -> str | None:
    if travel_mode:
        if left.travel_page and right.travel_page:
            if left.travel_page != right.travel_page:
                return None
            return "重复承载同一组旅行资料"
        left_scope = _itinerary_scope(left)
        right_scope = _itinerary_scope(right)
        if left_scope and right_scope and left_scope.isdisjoint(right_scope):
            return None

    title_sim = _similarity(left.title, right.title)
    objective_sim = _similarity(left.objective, right.objective)
    message_sim = _similarity(left.key_message, right.key_message)
    is_process_pair = left.visual_type in {"flow", "timeline"} and right.visual_type in {
        "flow",
        "timeline",
    }
    point_overlap = _point_overlap(
        left.key_points,
        right.key_points,
        match_threshold=0.42 if is_process_pair else 0.62,
    )

    if any(
        _similarity(left_point, right_point) >= 0.9
        for left_point in left.key_points
        for right_point in right.key_points
    ):
        return "包含重复的支撑要点"
    if title_sim >= 0.9 and objective_sim >= 0.68:
        return "标题和页面目标重复"
    if objective_sim >= 0.88 or message_sim >= 0.9:
        return "页面目标或核心判断重复"
    if point_overlap >= 0.5:
        return "多数支撑要点重复"
    if is_process_pair and point_overlap >= 0.4:
        return "流程步骤与阶段内容高度重合"

    left_evidence = _evidence_signatures(left)
    right_evidence = _evidence_signatures(right)
    if left_evidence and right_evidence:
        evidence_overlap = len(left_evidence & right_evidence) / min(
            len(left_evidence), len(right_evidence)
        )
        if evidence_overlap >= 0.9 and objective_sim >= 0.55:
            return "引用了同一组证据且页面目标相近"
    return None


def _point_overlap(
    left: list[str],
    right: list[str],
    *,
    match_threshold: float,
) -> float:
    if not left or not right:
        return 0.0
    candidates = sorted(
        (
            (_similarity(a, b), left_index, right_index)
            for left_index, a in enumerate(left)
            for right_index, b in enumerate(right)
        ),
        reverse=True,
    )
    used_left: set[int] = set()
    used_right: set[int] = set()
    matches = 0
    for similarity, left_index, right_index in candidates:
        if similarity < match_threshold:
            break
        if left_index in used_left or right_index in used_right:
            continue
        used_left.add(left_index)
        used_right.add(right_index)
        matches += 1
    return matches / min(len(left), len(right))


def _evidence_signatures(page: OutlinePageDraft) -> set[tuple[str, ...]]:
    return {
        (
            _normalize(item.source_ref),
            _normalize(item.metric),
            _normalize(item.category),
            _normalize(item.value),
            _normalize(item.unit),
            _normalize(item.period),
            _normalize(item.scope),
        )
        for item in page.evidence
        if item.quote
    }


def _similarity(left: str, right: str) -> float:
    a = _normalize(left)
    b = _normalize(right)
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b, autojunk=False).ratio()


def _normalize(value: str | None) -> str:
    return re.sub(r"[\W_]+", "", value or "").casefold()
