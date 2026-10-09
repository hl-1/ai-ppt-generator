from __future__ import annotations

import asyncio
import json
import logging
import uuid
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from app.domain.content import Slide
from app.domain.enterprise_layout import bind_planned_evidence, compose_report_slide
from app.domain.enterprise_quality import check_page_readability, check_planned_data
from app.domain.flex_fit import fit_tree_to_content
from app.domain.flex_width import fit_row_widths
from app.domain.image_planning import bind_page_image
from app.domain.outline import OutlinePageDraft
from app.domain.quality import check_evidence_alignment, check_slide_richness, is_repair_worthy
from app.domain.slide_draft import FlexSlideDraft, SlideDraft, draft_to_slide, flex_draft_to_slide
from app.domain.theme import resolve_theme
from app.domain.validation import StructureIssue, validate_slide
from app.llm.base import SlideGenerationInput, SlideGenerator
from app.llm.errors import (
    InvalidModelOutputError,
    InvalidSlideOutputError,
    LLMTimeoutError,
    LLMUnavailableError,
    safe_error_details,
)

# 只修一轮：结构 error 或过瘦/空话；主题模式额外修复溢出/容量 warning。
# generate 节点内部是 LCEL json_mode；校验与条件修复留在 Graph。
MAX_REPAIR_ROUNDS = 1
MAX_GENERATION_ATTEMPTS = 2
GENERATION_RETRY_DELAY_SECONDS = 2.0
logger = logging.getLogger(__name__)

MAX_SECTION_CHARS = 1_500
MAX_TOTAL_SOURCE_CHARS = 6_000


class SlideWorkflowState(TypedDict, total=False):
    input: SlideGenerationInput
    slide_id: str
    theme_id: str
    theme_overrides: dict[str, Any]
    draft: SlideDraft | FlexSlideDraft
    slide: Slide
    issues: list[StructureIssue]
    repairs: int
    repair_failed: bool


def prepare_slide_input(
    payload: SlideGenerationInput,
    *,
    max_total_chars: int = MAX_TOTAL_SOURCE_CHARS,
    max_section_chars: int = MAX_SECTION_CHARS,
) -> SlideGenerationInput:
    """裁剪单页可见的来源片段。

    单页只需要它引用到的少量证据，配额比大纲阶段小得多：
    上下文越短，模型越不容易把别页的内容混进来。
    """
    sections = []
    used = 0
    for section in payload.sections:
        text = " ".join(section.text.split())[:max_section_chars]
        if not text and not section.heading:
            continue
        remaining = max_total_chars - used
        if remaining <= 0:
            break
        text = text[:remaining]
        sections.append(section.model_copy(update={"text": text}))
        used += len(text)
    updates = {"sections": sections}
    if payload.travel_context and payload.layout_mode == "fixed":
        from app.services.travel_slides import is_itinerary_page

        if payload.page_title == "预算与缺价项目" or is_itinerary_page(payload.page_title):
            updates["layout_id"] = "table"
        elif payload.page_title in {"出行条件与安排总览", "预约待办与出发前核对"}:
            updates["layout_id"] = "bullets"
    return payload.model_copy(update=updates)


def build_slide_workflow(generator: SlideGenerator):
    """编译「准备 → 生成 → 校验 →（必要时）修复」的单页工作流。

    校验放进图里而不是调用方，是为了让修复轮次能拿到结构问题，
    形成一个自纠正回路而不是简单的重试。
    """

    async def prepare(state: SlideWorkflowState) -> dict:
        return {"input": prepare_slide_input(state["input"]), "repairs": 0, "repair_failed": False}

    def can_keep_previous(state: SlideWorkflowState) -> bool:
        return (
            bool(state.get("repairs", 0))
            and isinstance(state.get("slide"), Slide)
            and not any(issue.severity == "error" for issue in state.get("issues", []))
        )

    def keep_previous(state: SlideWorkflowState, error: Exception, *, stage: str) -> dict:
        if not can_keep_previous(state):
            raise error
        logger.warning(
            "slide repair fallback slide_id=%s position=%s stage=%s details=%s",
            state["slide_id"],
            state["input"].position,
            stage,
            safe_error_details(error),
        )
        return {
            "repair_failed": True,
            "issues": [
                *state.get("issues", []),
                StructureIssue(
                    severity="warning",
                    slide_id=state["slide_id"],
                    slot_id=None,
                    code="repair_failed",
                    message="自动修复未完成，已保留首轮可用内容，可稍后重试",
                ),
            ],
        }

    async def generate(state: SlideWorkflowState) -> dict:
        payload = state["input"]
        for attempt in range(1, MAX_GENERATION_ATTEMPTS + 1):
            try:
                draft = await generator.generate(payload)
                return {"draft": draft}
            except (LLMTimeoutError, LLMUnavailableError, InvalidModelOutputError) as error:
                details = safe_error_details(error)
                logger.warning(
                    "slide model request failed slide_id=%s position=%s repair=%s "
                    "attempt=%s/%s details=%s",
                    state["slide_id"],
                    payload.position,
                    bool(state.get("repairs", 0)),
                    attempt,
                    MAX_GENERATION_ATTEMPTS,
                    details,
                )
                if attempt == MAX_GENERATION_ATTEMPTS:
                    return keep_previous(state, error, stage="generate")
                if isinstance(error, InvalidModelOutputError):
                    feedback = (
                        "上一次输出未通过 JSON 或内容结构校验，请重新输出完整合法的 JSON；"
                        "字符串必须正确转义，diagram 只输出 nodes 和 edges，不输出 mermaid。"
                        f"校验信息：{json.dumps(details, ensure_ascii=False)}"
                    )
                    payload = payload.model_copy(update={"issues": [*payload.issues, feedback]})
                await asyncio.sleep(GENERATION_RETRY_DELAY_SECONDS)
            except Exception as error:
                return keep_previous(state, error, stage="generate")

    async def check_draft(state: SlideWorkflowState) -> dict:
        slide_id = uuid.UUID(state["slide_id"])
        draft = state["draft"]
        if isinstance(draft, FlexSlideDraft) or state["input"].layout_mode == "flex":
            if not isinstance(draft, FlexSlideDraft):
                raise InvalidSlideOutputError("灵活布局生成未返回 FlexSlideDraft")
            slide = flex_draft_to_slide(
                slide_id,
                draft,
                fallback_layout_id=state["input"].layout_id or "bullets",
            )
        else:
            if not isinstance(draft, SlideDraft):
                raise InvalidSlideOutputError("固定布局生成未返回 SlideDraft")
            slide = draft_to_slide(slide_id, state["input"].layout_id, draft)
        theme = resolve_theme(state.get("theme_id") or "ivory", state.get("theme_overrides"))
        payload = state["input"]
        if slide.layout_mode == "fixed":
            slide = slide.model_copy(
                update={
                    "blocks": [
                        block.model_copy(update={"text": payload.page_title})
                        if block.type == "text" and block.slot_id == "title"
                        else block
                        for block in slide.blocks
                    ]
                }
            )
        # 主题页以及显式指定流程/时间线的页面即使没有数值证据，也必须
        # 经过服务端的结构绑定与编排；否则它们会绕过 DiagramBlock 生成，
        # 退化成普通文本或保留表格的默认布局。
        enterprise = bool(
            payload.topic_mode
            or payload.key_message
            or payload.blueprint.core_message
            or payload.evidence
            or payload.evidence_kind in {"flow", "timeline"}
            or payload.visual_type in {"flow", "timeline"}
        )
        plan = OutlinePageDraft(
            title=payload.page_title,
            objective=payload.objective,
            key_points=payload.key_points,
            layout_id=payload.layout_id,
            page_role=payload.page_role,
            narrative_role=payload.narrative_role,
            evidence_kind=payload.evidence_kind,
            visual_type=payload.visual_type,
            key_message=payload.key_message,
            evidence=payload.evidence,
            visual=payload.visual_hint,
            image_plan=payload.image_plan,
        )
        slide = bind_page_image(slide, plan)
        travel_budget = payload.travel_context and payload.page_title == "预算与缺价项目"
        travel_cover = payload.travel_context and payload.page_role == "cover"
        from app.services.travel_slides import CORE_TRAVEL_PAGES, is_itinerary_page

        travel_itinerary = payload.travel_context and is_itinerary_page(payload.page_title)
        if travel_budget or travel_itinerary:
            from app.domain.block_style import BlockStyle

            slide = slide.model_copy(
                update={
                    "blocks": [
                        block.model_copy(update={"style": BlockStyle(size_pt=14)})
                        if block.type == "table"
                        else block
                        for block in slide.blocks
                    ]
                }
            )
        structured_travel = payload.travel_context and (
            payload.page_title in CORE_TRAVEL_PAGES or travel_cover or travel_itinerary
        )
        if slide.layout_mode == "flex" and not structured_travel:
            if enterprise:
                labels = {
                    s.ref: " · ".join(filter(None, [s.heading, s.locator, s.ref]))
                    for s in payload.sections
                }
                slide = bind_planned_evidence(
                    slide,
                    plan,
                    labels,
                    topic_mode=payload.topic_mode,
                )
            slide = compose_report_slide(
                slide,
                plan,
                layout_template=payload.layout_template,
                curate=enterprise,
                decision_request=payload.blueprint.decision_request,
            )
        # 生成期先定列宽再定行高：宽度决定折行，折行决定自然高度。
        # 两步都放在校验之前，让溢出/容量告警反映的是最终版面。
        if slide.layout_mode == "flex" and slide.layout_tree is not None:
            widened = fit_row_widths(slide.layout_tree, slide.blocks, theme=theme)
            slide = slide.model_copy(
                update={
                    "layout_tree": fit_tree_to_content(
                        widened,
                        slide.blocks,
                        theme=theme,
                        page_role=payload.page_role,
                    )
                }
            )
        issues = validate_slide(slide, theme=theme)
        if payload.travel_context:
            from app.services.travel_planning import travel_claim_issues

            text = json.dumps(
                [block.model_dump(mode="json") for block in slide.blocks], ensure_ascii=False
            )
            issues.extend(
                StructureIssue(
                    severity="error",
                    slide_id=str(slide.id),
                    slot_id=None,
                    code="travel_unverified_claim",
                    message=message,
                )
                for message in travel_claim_issues(text, payload.travel_context)
            )
        if enterprise:
            issues.extend(check_planned_data(slide, plan))
        issues.extend(check_page_readability(slide))
        issues.extend(
            check_evidence_alignment(
                slide,
                payload.evidence_kind,
                summary_metrics=payload.visual_type == "auto"
                and (
                    payload.page_role == "summary"
                    or payload.narrative_role in {"executive_summary", "summary", "decision"}
                ),
            )
        )
        issues.extend(
            check_slide_richness(
                slide,
                content_density=payload.content_density,
                page_role=payload.page_role,
            )
        )
        return {
            "slide": slide,
            "issues": issues,
        }

    async def check(state: SlideWorkflowState) -> dict:
        try:
            checked = await check_draft(state)
            if can_keep_previous(state) and any(
                issue.severity == "error" for issue in checked["issues"]
            ):
                return keep_previous(
                    state, InvalidSlideOutputError("修复结果未通过结构校验"), stage="check"
                )
            return checked
        except Exception as error:
            return keep_previous(state, error, stage="check")

    async def repair(state: SlideWorkflowState) -> dict:
        topic_mode = state["input"].topic_mode
        repairable = [
            issue for issue in state["issues"] if is_repair_worthy(issue, topic_mode=topic_mode)
        ]
        messages = [_describe(issue) for issue in repairable]
        repaired = state["input"].model_copy(
            update={
                "issues": messages,
                "previous_draft": state["draft"].model_dump(mode="json"),
            }
        )
        return {"input": repaired, "repairs": state.get("repairs", 0) + 1}

    def route(state: SlideWorkflowState) -> str:
        if state.get("repairs", 0) >= MAX_REPAIR_ROUNDS:
            return END
        if any(
            is_repair_worthy(issue, topic_mode=state["input"].topic_mode)
            for issue in state["issues"]
        ):
            return "repair"
        return END

    graph = StateGraph(SlideWorkflowState)
    graph.add_node("prepare", prepare)
    graph.add_node("generate", generate)
    graph.add_node("check", check)
    graph.add_node("repair", repair)
    graph.add_edge(START, "prepare")
    graph.add_edge("prepare", "generate")
    graph.add_conditional_edges(
        "generate",
        lambda state: END if state.get("repair_failed") else "check",
        {"check": "check", END: END},
    )
    graph.add_conditional_edges("check", route, {"repair": "repair", END: END})
    graph.add_edge("repair", "generate")
    return graph.compile()


async def run_slide_workflow(
    workflow,
    payload: SlideGenerationInput,
    slide_id: uuid.UUID,
    *,
    theme_id: str | None = None,
    theme_overrides: dict[str, Any] | None = None,
) -> tuple[Slide, list[StructureIssue]]:
    result = await workflow.ainvoke(
        {
            "input": payload,
            "slide_id": str(slide_id),
            "theme_id": theme_id or "ivory",
            "theme_overrides": theme_overrides or {},
        }
    )
    slide = result.get("slide")
    if not isinstance(slide, Slide):
        raise InvalidSlideOutputError("页面工作流未产出内容")
    if any(issue.code == "travel_unverified_claim" for issue in result.get("issues") or []):
        raise InvalidSlideOutputError("旅游页面仍包含无法对应来源的价格或时间")
    if payload.travel_context:
        manifest = "\n".join(
            f"{source['id']} {source['title']} {source['url']}"
            for source in payload.travel_context.get("sources", [])
        )
        slide = slide.model_copy(
            update={
                "speaker_notes": f"{slide.speaker_notes or ''}\n\n"
                f"旅行资料版本：{payload.travel_context['version']}\n"
                f"价格按官方规则/报价/估算/待查询分别标记。"
                f"游览时段为建议。\n资料来源：\n{manifest}"
            }
        )
    return slide, list(result.get("issues") or [])


def _describe(issue: StructureIssue) -> str:
    scope = f"槽位 {issue.slot_id}" if issue.slot_id else "本页"
    return f"{scope}：{issue.message}"
