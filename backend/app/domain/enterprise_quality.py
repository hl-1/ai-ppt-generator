"""Deck-level narrative, evidence and visual rhythm checks."""

from __future__ import annotations

from collections.abc import Mapping

from app.domain.content import Deck, Slide
from app.domain.evidence import (
    check_evidence_conflicts,
    comparable_categories,
    comparable_series,
    evidence_problem,
)
from app.domain.outline import DeckBlueprint, OutlinePage, OutlinePageDraft, ReportBrief
from app.domain.quality import _slide_body_text
from app.domain.slide_geometry import placed_by_block_id
from app.domain.validation import StructureIssue


def check_planned_data(slide: Slide, plan: OutlinePageDraft) -> list[StructureIssue]:
    """核对固定/灵活布局及人工改动后的结构化数据，不能只在生成时验证。"""
    issues = []
    series = comparable_series(plan.evidence)
    categories = comparable_categories(plan.evidence)
    for block in slide.blocks:
        matches = True
        if block.type == "chart":
            planned = series if block.chart_type == "line" else categories
            matches = bool(planned) and (
                block.categories
                == [e.period if block.chart_type == "line" else e.category for e in planned]
                and block.unit == planned[0].unit
                and len(block.series) == 1
                and block.series[0].name == planned[0].metric
                and block.series[0].values
                == [float(e.value.replace(",", "").rstrip("%％")) for e in planned]
            )
        elif block.type == "kpi":
            matches = any(
                e.value
                and e.metric == block.label
                and block.value.replace(" ", "").replace("％", "%")
                == (e.value if e.value.endswith(("%", "％")) else e.value + e.unit)
                .replace(" ", "")
                .replace("％", "%")
                for e in plan.evidence
            )
        if not matches:
            issues.append(
                StructureIssue(
                    severity="error",
                    slide_id=slide.id,
                    slot_id=block.id,
                    code="evidence_data_mismatch",
                    message="图表或指标与已绑定证据的数值、指标、单位或时间不一致，请核对后再导出",
                )
            )
    return issues


def check_page_readability(slide: Slide) -> list[StructureIssue]:
    issues: list[StructureIssue] = []

    def issue(code: str, message: str, block_id: str | None = None, severity="warning"):
        issues.append(
            StructureIssue(
                code=code,
                message=message,
                slide_id=slide.id,
                slot_id=block_id,
                severity=severity,
            )
        )

    if len(_slide_body_text(slide)) > 950:
        issue("dense_page", "页面信息较密，建议将支撑细节移至讲稿或拆页，保留核心结论与证据")
    for block in slide.blocks:
        if block.type == "chart":
            if (
                not block.categories
                or not block.series
                or any(len(s.values) != len(block.categories) for s in block.series)
            ):
                issue(
                    "chart_data", "图表分类与数据长度不一致，不能补零或截断导出", block.id, "error"
                )
            if len(block.categories) > 10 or len(block.series) > 4:
                issue("dense_chart", "图表分类或系列过多，建议突出重点并拆分其余数据", block.id)
        if block.type == "table":
            if any(len(row) != len(block.header) for row in block.rows):
                issue("table_data", "表格行列长度不一致，请补齐对应单元格", block.id, "error")
            if len(block.rows) > 8 or len(block.header) > 6:
                issue("dense_table", "表格较密，建议展示关键行列并将明细放入附录", block.id)
    try:
        placed = placed_by_block_id(slide)
    except (KeyError, ValueError):
        return issues
    text_blocks = [b for b in slide.blocks if b.type in {"text", "bullets"} and b.id in placed]
    for i, left in enumerate(text_blocks):
        a = placed[left.id].rect
        for right in text_blocks[i + 1 :]:
            b = placed[right.id].rect
            width = max(0, min(a.x + a.w, b.x + b.w) - max(a.x, b.x))
            height = max(0, min(a.y + a.h, b.y + b.h) - max(a.y, b.y))
            if width * height > 0.15 * min(a.w * a.h, b.w * b.h) > 0:
                issue(
                    "text_overlap",
                    f"文字区域 {left.id} 与 {right.id} 明显重叠，请调整位置",
                    right.id,
                    "error",
                )
    return issues


def check_report_quality(
    deck: Deck,
    plans: Mapping[str, OutlinePage],
    sources: Mapping[str, str],
    blueprint: DeckBlueprint,
    brief: ReportBrief,
) -> list[StructureIssue]:
    issues: list[StructureIssue] = []

    def warn(code: str, message: str, slide_id: str = "", severity="warning"):
        issues.append(
            StructureIssue(
                severity=severity,
                slide_id=slide_id,
                slot_id=None,
                code=code,
                message=message,
            )
        )

    active = [plans[s.id] for s in deck.slides if s.id in plans]
    enterprise = brief.scenario != "general" or bool(blueprint.core_message)
    if enterprise and len(active) >= 5:
        roles = {p.narrative_role for p in active}
        if "executive_summary" not in roles:
            warn("missing_summary", "整套汇报缺少执行摘要，建议先说明核心判断与支撑结果")
        if not any(
            p.page_role == "summary" or p.narrative_role in {"summary", "action", "decision"}
            for p in active[-2:]
        ):
            warn("missing_close", "结尾尚未收束结论或下一步，请回应汇报目的")
        if (brief.decision_request or blueprint.decision_request) and "decision" not in roles:
            warn("missing_decision", "已填写决策诉求，但整套汇报缺少明确的决策页")
    all_evidence = [e for page in active for e in page.evidence]
    for conflict in check_evidence_conflicts(all_evidence):
        warn("evidence_conflict", conflict, severity="error")
    previous_signature = None
    layout_run = 0
    text_run = 0
    for slide in deck.slides:
        issues.extend(check_page_readability(slide))
        plan = plans.get(slide.id)
        if plan and (enterprise or plan.key_message or plan.evidence):
            issues.extend(check_planned_data(slide, plan))
        if plan and plan.page_role in {"cover", "toc", "section"}:
            previous_signature = None
            layout_run = text_run = 0
            continue
        if plan:
            for note in plan.planning_notes:
                warn("evidence_gap", note, slide.id)
            for evidence in plan.evidence:
                problem = evidence_problem(evidence, sources)
                if problem:
                    warn("source_mismatch", problem, slide.id, severity="error")
            if (
                plan.key_message
                and not plan.evidence
                and plan.narrative_role
                in {
                    "performance",
                    "driver",
                }
            ):
                warn("unsupported_conclusion", "分析结论尚未绑定原句证据，请核对支撑材料", slide.id)
            if plan.evidence and not any(
                (b.type == "callout" and b.variant == "source")
                or (b.type == "text" and "来源" in b.text)
                for b in slide.blocks
            ):
                warn(
                    "missing_source_label", "本页有数据证据，建议在页面显示来源与统计时间", slide.id
                )
        types = tuple(
            b.type for b in slide.blocks if not (b.type == "callout" and b.variant == "source")
        )
        signature = (slide.layout_id, types, _tree_shape(slide.layout_tree))
        layout_run = layout_run + 1 if signature == previous_signature else 1
        previous_signature = signature
        if layout_run == 3:
            warn("repeated_layout", "连续三页使用相同结构，建议结合内容调整表达节奏", slide.id)
        text_run = text_run + 1 if set(types) <= {"text", "bullets", "callout"} else 0
        if text_run == 3:
            warn(
                "text_sequence",
                "连续三页以文字为主，可用对比或流程表达关系；没有数据时无需凑图表",
                slide.id,
            )
    return issues


def _tree_shape(node):
    if node is None:
        return None
    if node.type == "block":
        return "block"
    return (node.type, tuple(_tree_shape(child) for child in node.children))
