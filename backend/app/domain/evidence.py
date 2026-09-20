"""Deterministic source checks and conservative chart eligibility."""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Mapping
from decimal import Decimal, InvalidOperation

from app.domain.outline import EvidenceItem, OutlinePageDraft

NUMBER = re.compile(r"(?<![\w.])-?\d+(?:,\d{3})*(?:\.\d+)?(?:[%％])?(?![\d.])")


def compact(text: str) -> str:
    return re.sub(r"\s+", "", text).replace("％", "%").replace(",", "")


def numeric_value(value: str) -> Decimal | None:
    try:
        result = Decimal(value.replace(",", "").rstrip("%％"))
        return result if result.is_finite() else None
    except InvalidOperation:
        return None


def evidence_problem(item: EvidenceItem, sources: Mapping[str, str]) -> str | None:
    source = sources.get(item.source_ref)
    if source is None or compact(item.quote) not in compact(source):
        return "引用原句未在指定来源中找到"
    if item.value:
        value = numeric_value(item.value)
        # 汉字旁的数字也要保留；不能将 12 匹配成 120、12% 匹配成 12 万元。
        tokens = re.findall(r"-?\d+(?:,\d{3})*(?:\.\d+)?(?:[%％])?", item.quote)
        percent = item.value.endswith(("%", "％")) or item.unit in {"%", "％"}
        if value is None or not any(
            numeric_value(token) == value and token.endswith(("%", "％")) == percent
            for token in tokens
        ):
            return "数据值或百分比单位与引用原句不符"
        for label, field in (
            ("指标", item.metric),
            ("分类", item.category),
            ("单位", item.unit),
            ("时间", item.period),
            ("统计范围", item.scope),
        ):
            if field and compact(field) not in compact(item.quote):
                return f"{label}未出现在引用原句中"
    return None


def comparable_series(items: list[EvidenceItem]) -> list[EvidenceItem]:
    """只接受同指标/单位/范围且时间不重复的完整序列，不混用口径。"""
    numeric = [e for e in items if e.value and numeric_value(e.value) is not None]
    if len(numeric) < 2 or any(not e.metric or not e.unit or not e.period for e in numeric):
        return []
    if len({(e.metric, e.unit, e.scope) for e in numeric}) != 1:
        return []
    if len({e.period for e in numeric}) != len(numeric):
        return []
    # 保留来源/大纲中的次序，避免用字符串大小代替真实日期顺序。
    return numeric


def comparable_categories(items: list[EvidenceItem]) -> list[EvidenceItem]:
    """返回同指标/单位/范围下的分类序列，供构成图或横向比较使用。"""
    numeric = [e for e in items if e.value and e.metric and e.unit and e.category]
    if len(numeric) < 2 or len({(e.metric, e.unit, e.scope) for e in numeric}) != 1:
        return []
    if len({e.category for e in numeric}) != len(numeric):
        return []
    return numeric


def check_evidence_conflicts(items: list[EvidenceItem]) -> list[str]:
    values: dict[tuple, set[Decimal | None]] = defaultdict(set)
    for item in items:
        if item.value and item.metric and item.period:
            values[(item.metric, item.unit, item.period, item.scope)].add(numeric_value(item.value))
    return [
        f"{key[0]}（{key[2]}，{key[1]}）存在不同数值，请核对来源口径"
        for key, found in values.items()
        if len(found) > 1
    ]


def prepare_page_plan(page: OutlinePageDraft, sources: Mapping[str, str]) -> OutlinePageDraft:
    """无充分证据时回退到定性表达，把缺口留给大纲编辑端。"""
    notes: list[str] = []
    valid: list[EvidenceItem] = []
    for item in page.evidence:
        problem = evidence_problem(item, sources)
        if problem:
            notes.append(f"{item.source_ref}：{problem}")
        else:
            valid.append(item)
    conflicts = check_evidence_conflicts(valid)
    notes.extend(conflicts)
    kind = page.evidence_kind
    numeric = [e for e in valid if e.value and e.metric and e.unit]
    if kind in {"trend", "chart"} and (not comparable_series(valid) or conflicts):
        notes.append("可比数据不足，已改为定性分析；补齐同指标、单位、时间与范围后可使用趋势图")
        kind = "narrative"
    if kind in {"composition", "comparison"} and (
        not comparable_categories(valid) or conflicts
    ):
        notes.append("缺少可比较的分类数据，已改为定性分析；补齐分类、指标、单位与范围后可使用图表")
        kind = "narrative"
    if kind in {"flow", "timeline"} and len(page.key_points) < 2:
        notes.append("流程或阶段信息不足，已改为定性分析；至少需要两个步骤或阶段")
        kind = "narrative"
    if kind == "kpi" and (not numeric or conflicts):
        notes.append("缺少可追溯指标，已改为定性分析")
        kind = "narrative"
    refs = list(dict.fromkeys([*page.source_refs, *(e.source_ref for e in valid)]))
    refs = [ref for ref in refs if ref in sources][:10]
    visual = page.visual
    if kind in {
        "trend",
        "chart",
        "composition",
        "comparison",
        "flow",
        "timeline",
        "kpi",
        "table",
        "actions",
    }:
        visual = None
    layout = page.layout_id
    # 避免 fixed 模式回退后仍被必填图表槽位要求制造数据。
    if kind == "narrative" and layout in {"chart", "kpi"}:
        layout = "bullets"
    return page.model_copy(
        update={
            "evidence": valid,
            "source_refs": refs,
            "evidence_kind": kind,
            "visual": visual,
            "layout_id": layout,
            "planning_notes": list(dict.fromkeys(notes))[:16],
        }
    )
