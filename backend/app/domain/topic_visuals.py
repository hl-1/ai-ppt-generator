"""Deterministic visual planning using user-supplied topic evidence."""

from __future__ import annotations

import re
from collections.abc import Mapping

from app.domain.outline import EvidenceItem, OutlinePageDraft

VisualType = str

VISUAL_TO_EVIDENCE = {
    "line": "trend",
    "pie": "composition",
    "bar": "comparison",
    "column": "comparison",
    "flow": "flow",
    "timeline": "timeline",
    "financial_table": "table",
    "waterfall": "waterfall",
    "combo_chart": "comparison",
}

TOPIC_VISUAL_ORDER = ("line", "column", "pie", "bar", "flow", "timeline")

_FIELD_RE = re.compile(
    r"指标：(?P<metric>[^；。]+)；"
    r"分类：(?P<category>[^；。]*)；"
    r"数值：(?P<value>[^；。]+)；"
    r"单位：(?P<unit>[^；。]+)；"
    r"时间：(?P<period>[^；。]+)；"
    r"范围：(?P<scope>[^；。]+)"
)


def evidence_kind_for_visual(visual_type: VisualType) -> str | None:
    return VISUAL_TO_EVIDENCE.get(visual_type)


def topic_visual_evidence(
    sources: Mapping[str, str],
    visual_type: VisualType,
    *,
    used_signatures: set[tuple] | None = None,
) -> list[EvidenceItem]:
    """Extract structured numeric records supplied with the topic."""
    if visual_type not in {"line", "column", "bar", "pie", "combo_chart"}:
        return []

    records: list[EvidenceItem] = []
    for source_ref, text in sources.items():
        for match in _FIELD_RE.finditer(text):
            line = match.group(0).strip()
            fields = match.groupdict()
            records.append(
                EvidenceItem(
                    source_ref=source_ref,
                    quote=line,
                    metric=fields["metric"].strip(),
                    category=fields["category"].strip(),
                    value=fields["value"].strip(),
                    unit=fields["unit"].strip(),
                    period=fields["period"].strip(),
                    scope=fields["scope"].strip(),
                )
            )

    groups: dict[tuple[str, str, str, str], list[EvidenceItem]] = {}
    for item in records:
        key = (
            item.metric,
            item.unit,
            item.scope,
            item.period if visual_type == "pie" else "",
        )
        groups.setdefault(key, []).append(item)

    candidates: list[list[EvidenceItem]] = []
    for items in groups.values():
        if visual_type in {"line", "combo_chart"}:
            if len({item.period for item in items}) >= 2:
                candidates.append(items)
        elif len({item.category for item in items}) >= 2:
            candidates.append(items)

    candidates.sort(
        key=lambda items: (
            -_metric_preference(visual_type, items[0].metric),
            -len(items),
            items[0].metric,
            items[0].period,
            items[0].category,
        )
    )
    if visual_type == "combo_chart":
        for index, left in enumerate(candidates):
            for right in candidates[index + 1 :]:
                if (
                    left[0].metric != right[0].metric
                    and left[0].scope == right[0].scope
                    and {item.period for item in left} == {item.period for item in right}
                    and len(left) + len(right) <= 12
                ):
                    return [*left, *right]
        return []
    for items in candidates:
        signature = (
            tuple((item.metric, item.category, item.period, item.value) for item in items),
        )
        if used_signatures is not None and signature in used_signatures:
            continue
        if used_signatures is not None:
            used_signatures.add(signature)
        return items[:12]
    return []


def _metric_preference(visual_type: VisualType, metric: str) -> int:
    preferred = {
        "pie": ("资源", "结构", "投入", "构成"),
        "bar": ("准备度", "对比", "排名"),
        "column": ("采用率", "能力", "准备度"),
        "line": ("成熟度", "增长", "采用率"),
    }.get(visual_type, ())
    return sum(1 for word in preferred if word in metric)


def _compatible_evidence(items: list[EvidenceItem], visual_type: VisualType) -> bool:
    numeric = [item for item in items if item.value and item.metric and item.unit]
    if visual_type in {"line", "combo_chart"}:
        from app.domain.evidence import comparable_metric_series

        groups = comparable_metric_series(numeric)
        if visual_type == "line":
            return bool(groups) and sum(len(group) for group in groups) == len(numeric)
        return len(groups) >= 2 and len({tuple(e.period for e in group) for group in groups}) == 1
    if len(numeric) < 2 or len({(item.metric, item.unit, item.scope) for item in numeric}) != 1:
        return False
    return len({item.category for item in numeric if item.category}) >= 2


def normalize_topic_pages(
    pages: list[OutlinePageDraft],
    sources: Mapping[str, str],
) -> list[OutlinePageDraft]:
    """Choose visual forms from the page's purpose and evidence."""
    result: list[OutlinePageDraft] = []

    for page in pages:
        if page.visual_type in {"photo", "illustration"} or page.image_plan:
            result.append(page)
            continue
        if page.page_role in {"cover", "toc", "section"}:
            result.append(page.model_copy(update={"visual_type": "auto"}))
            continue

        visual_type = page.visual_type
        if visual_type == "auto" and (
            page.page_role == "summary"
            or page.narrative_role in {"executive_summary", "summary", "decision", "risk", "driver"}
            or page.evidence_kind in {"kpi", "actions", "table"}
            or (page.narrative_role == "action" and page.evidence_kind not in {"flow", "timeline"})
        ):
            result.append(page)
            continue
        page_sources = {ref: sources[ref] for ref in page.source_refs if ref in sources} or sources
        if visual_type == "auto":
            visual_type = _suggest_visual(page, page_sources)

        kind = evidence_kind_for_visual(visual_type)
        evidence = page.evidence
        if visual_type in {"line", "column", "bar", "pie", "combo_chart"}:
            if not _compatible_evidence(evidence, visual_type):
                extracted = topic_visual_evidence(
                    page_sources,
                    visual_type,
                )
                if extracted:
                    evidence = extracted
                elif not evidence:
                    visual_type = "auto"
                    kind = None
        result.append(
            page.model_copy(
                update={
                    "visual_type": visual_type,
                    "evidence_kind": kind or page.evidence_kind,
                    "evidence": evidence,
                    "planning_notes": [],
                }
            )
        )
    return result


def normalize_topic_page(
    page: OutlinePageDraft,
    sources: Mapping[str, str],
) -> OutlinePageDraft:
    """Normalize one edited topic page without changing the other pages."""
    normalized = normalize_topic_pages([page], sources)[0]
    visual_type = normalized.visual_type
    kind = evidence_kind_for_visual(visual_type)
    if kind:
        normalized = normalized.model_copy(update={"evidence_kind": kind})
    return normalized


def _suggest_visual(
    page: OutlinePageDraft,
    sources: Mapping[str, str],
) -> str:
    if page.evidence_kind in {"flow", "timeline"}:
        return page.evidence_kind
    blob = " ".join([page.title, page.objective, page.key_message, *page.key_points])
    if any(
        word in blob for word in ("双指标", "双线", "成熟度与采用率", "指标与率")
    ) and topic_visual_evidence(sources, "combo_chart"):
        return "combo_chart"
    keyword_map = (
        (("分流", "审批", "并行", "汇聚"), "flow"),
        (("里程碑", "阶段安排", "时间轴"), "timeline"),
        (("构成", "结构", "占比", "资源"), "pie"),
        (("对比", "比较", "对象", "差异", "排名"), "bar"),
        (("采用率", "增长", "成熟度", "变化", "趋势"), "line"),
    )
    for keywords, visual_type in keyword_map:
        if any(keyword in blob for keyword in keywords):
            if visual_type in {"line", "column", "bar", "pie"} and not topic_visual_evidence(
                sources, visual_type
            ):
                continue
            return visual_type

    return "auto"
