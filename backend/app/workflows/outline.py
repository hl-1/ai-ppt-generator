from __future__ import annotations

from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from app.domain.evidence import prepare_page_plan
from app.domain.image_planning import plan_page_image
from app.domain.outline import OutlineDraft
from app.domain.topic_uniqueness import find_duplicate_topic_pages
from app.domain.topic_visuals import normalize_topic_pages
from app.llm.base import OutlineGenerationInput, OutlineGenerator, OutlineSourceSection
from app.llm.errors import InvalidOutlineOutputError

# 总预算压住 prompt 体积，单节上限避免某一节吞掉全部配额；
# 按整节追加，超长只截断该节正文，保证 ref 与文本不会错位。
MAX_TOTAL_SOURCE_CHARS = 12_000
MAX_SECTION_CHARS = 2_000


class OutlineWorkflowState(TypedDict, total=False):
    input: OutlineGenerationInput
    prepared: OutlineGenerationInput
    draft: OutlineDraft


def prepare_outline_input(
    payload: OutlineGenerationInput,
    *,
    max_total_chars: int = MAX_TOTAL_SOURCE_CHARS,
    max_section_chars: int = MAX_SECTION_CHARS,
) -> OutlineGenerationInput:
    """清理并裁剪来源小节，供大纲准备流程与单测共用。"""
    prepared_sections: list[OutlineSourceSection] = []
    used_chars = 0

    for section in payload.sections:
        heading = section.heading.strip() if section.heading else None
        text = " ".join(section.text.split())
        locator = section.locator.strip()

        if not text and not heading:
            continue

        if len(text) > max_section_chars:
            text = text[:max_section_chars]

        remaining = max_total_chars - used_chars
        if remaining <= 0:
            break

        heading_len = len(heading or "")
        # 标题本身已超出剩余预算时停止，避免截断 heading 造成语义残缺
        if heading_len > remaining:
            break

        text_budget = min(len(text), remaining - heading_len)
        text = text[:text_budget]
        section_cost = len(text) + heading_len
        if section_cost <= 0:
            break

        prepared_sections.append(
            OutlineSourceSection(
                ref=section.ref,
                heading=heading,
                level=section.level,
                text=text,
                locator=locator,
            )
        )
        used_chars += section_cost
        if used_chars >= max_total_chars:
            break

    return payload.model_copy(update={"sections": prepared_sections})


def build_outline_workflow(generator: OutlineGenerator):
    """编译「准备输入 → 调用生成器」的大纲工作流。

    一次结构化生成走 LCEL json_mode；本 Graph 只负责裁剪来源后再调用。
    """

    async def prepare(state: OutlineWorkflowState) -> dict[str, OutlineGenerationInput]:
        return {"prepared": prepare_outline_input(state["input"])}

    async def generate(state: OutlineWorkflowState) -> dict[str, OutlineDraft]:
        payload = state["prepared"]
        sources = {section.ref: section.text for section in payload.sections}
        if payload.travel_context:
            from app.services.travel_outline import build_travel_outline

            draft = build_travel_outline(payload)
        else:
            draft = await generator.generate(payload)
        for repair_round in range(3):
            pages = [plan_page_image(page, deck_title=payload.title) for page in draft.pages]
            if payload.travel_context:
                from app.domain.outline import ImagePlan

                pages = [
                    page.model_copy(
                        update={
                            "visual_type": "photo",
                            "image_plan": ImagePlan(
                                subject=page.image_plan.subject,
                                queries=page.image_plan.queries,
                                source="stock",
                                require_real=True,
                                purpose=page.image_plan.purpose,
                            ),
                        }
                    )
                    if page.image_plan
                    else page
                    for page in pages
                ]
            if payload.topic_mode:
                pages = normalize_topic_pages(pages, sources)
            pages = [
                prepare_page_plan(page, sources, topic_mode=payload.topic_mode) for page in pages
            ]
            draft = draft.model_copy(update={"pages": pages})
            duplicates = find_duplicate_topic_pages(pages) if payload.topic_mode else []
            if payload.travel_context:
                from app.services.travel_planning import travel_claim_issues

                for page in pages:
                    text = " ".join(
                        [page.title, page.objective, page.key_message, *page.key_points]
                    )
                    duplicates.extend(travel_claim_issues(text, payload.travel_context))
            if not duplicates:
                return {"draft": draft}
            if repair_round == 2:
                if payload.travel_context:
                    raise InvalidOutlineOutputError("旅游大纲仍包含无依据的价格、时间或重复页面")
                raise InvalidOutlineOutputError("主题大纲经两轮修复后仍有重复页面，未保存重复内容")
            payload = payload.model_copy(
                update={
                    "issues": duplicates,
                    "previous_draft": draft.model_dump(mode="json"),
                }
            )
            draft = await generator.generate(payload)
        raise InvalidOutlineOutputError("主题大纲重复校验未通过")

    graph = StateGraph(OutlineWorkflowState)
    graph.add_node("prepare", prepare)
    graph.add_node("generate", generate)
    graph.add_edge(START, "prepare")
    graph.add_edge("prepare", "generate")
    graph.add_edge("generate", END)
    return graph.compile()


async def run_outline_workflow(
    workflow,
    payload: OutlineGenerationInput,
) -> OutlineDraft:
    """异步调用封装：输入生成参数，返回校验后的大纲草稿。"""
    result = await workflow.ainvoke({"input": payload})
    draft = result.get("draft")
    if not isinstance(draft, OutlineDraft):
        raise RuntimeError("大纲工作流未产出 OutlineDraft")
    return draft
