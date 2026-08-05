from __future__ import annotations

import uuid
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from app.domain.content import Slide
from app.domain.slide_draft import SlideDraft, draft_to_slide
from app.domain.validation import StructureIssue, validate_slide
from app.llm.base import SlideGenerationInput, SlideGenerator
from app.llm.errors import InvalidSlideOutputError

# 只修一轮：结构问题多为容量超限，一次定向反馈通常够用；
# 反复重试只会线性放大延迟与成本，不如把这一页标记失败交给用户重试。
MAX_REPAIR_ROUNDS = 1

MAX_SECTION_CHARS = 1_500
MAX_TOTAL_SOURCE_CHARS = 6_000


class SlideWorkflowState(TypedDict, total=False):
    input: SlideGenerationInput
    slide_id: str
    draft: SlideDraft
    slide: Slide
    issues: list[StructureIssue]
    repairs: int


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
    return payload.model_copy(update={"sections": sections})


def build_slide_workflow(generator: SlideGenerator):
    """编译「准备 → 生成 → 校验 →（必要时）修复」的单页工作流。

    校验放进图里而不是调用方，是为了让修复轮次能拿到结构问题，
    形成一个自纠正回路而不是简单的重试。
    """

    async def prepare(state: SlideWorkflowState) -> dict:
        return {"input": prepare_slide_input(state["input"]), "repairs": 0}

    async def generate(state: SlideWorkflowState) -> dict:
        draft = await generator.generate(state["input"])
        return {"draft": draft}

    async def check(state: SlideWorkflowState) -> dict:
        slide_id = uuid.UUID(state["slide_id"])
        slide = draft_to_slide(slide_id, state["input"].layout_id, state["draft"])
        return {"slide": slide, "issues": validate_slide(slide)}

    async def repair(state: SlideWorkflowState) -> dict:
        messages = [_describe(issue) for issue in state["issues"]]
        repaired = state["input"].model_copy(update={"issues": messages})
        return {"input": repaired, "repairs": state.get("repairs", 0) + 1}

    def route(state: SlideWorkflowState) -> str:
        if not state["issues"]:
            return END
        if state.get("repairs", 0) >= MAX_REPAIR_ROUNDS:
            return END
        return "repair"

    graph = StateGraph(SlideWorkflowState)
    graph.add_node("prepare", prepare)
    graph.add_node("generate", generate)
    graph.add_node("check", check)
    graph.add_node("repair", repair)
    graph.add_edge(START, "prepare")
    graph.add_edge("prepare", "generate")
    graph.add_edge("generate", "check")
    graph.add_conditional_edges("check", route, {"repair": "repair", END: END})
    graph.add_edge("repair", "generate")
    return graph.compile()


async def run_slide_workflow(
    workflow,
    payload: SlideGenerationInput,
    slide_id: uuid.UUID,
) -> tuple[Slide, list[StructureIssue]]:
    result = await workflow.ainvoke({"input": payload, "slide_id": str(slide_id)})
    slide = result.get("slide")
    if not isinstance(slide, Slide):
        raise InvalidSlideOutputError("页面工作流未产出内容")
    return slide, list(result.get("issues") or [])


def _describe(issue: StructureIssue) -> str:
    scope = f"槽位 {issue.slot_id}" if issue.slot_id else "本页"
    return f"{scope}：{issue.message}"
