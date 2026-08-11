from __future__ import annotations

from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph
from pydantic import TypeAdapter

from app.domain.content import Block, Slide
from app.domain.flex_layout import FlexContainer
from app.domain.slide_patch import (
    BlockPatch,
    DiscardedPatch,
    apply_patches,
    filter_patches,
)
from app.domain.theme import resolve_theme
from app.domain.validation import StructureIssue, has_blocking_issue, validate_slide
from app.llm.base import SlideEditGenerator, SlideEditInput
from app.llm.errors import InvalidSlideEditOutputError

# 与整页生成一致：只修一轮，避免线性放大延迟与成本
MAX_REPAIR_ROUNDS = 1

_blocks_adapter = TypeAdapter(list[Block])


class SlideEditWorkflowState(TypedDict, total=False):
    input: SlideEditInput
    slide_id: str
    layout_id: str
    layout_mode: str
    layout_tree: FlexContainer | None
    theme_id: str
    theme_overrides: dict[str, Any]
    original_blocks: list[Block]
    operations: list[BlockPatch]
    discarded: list[DiscardedPatch]
    patched_blocks: list[Block]
    issues: list[StructureIssue]
    repairs: int


def build_slide_edit_workflow(generator: SlideEditGenerator):
    """编译「生成操作清单 → 应用到副本并校验 →（必要时）修复一轮」。"""

    async def generate(state: SlideEditWorkflowState) -> dict:
        operations = await generator.generate(state["input"])
        return {"operations": operations, "repairs": state.get("repairs", 0)}

    async def check(state: SlideEditWorkflowState) -> dict:
        filtered = filter_patches(state["original_blocks"], state["operations"])
        patched = apply_patches(state["original_blocks"], filtered.accepted)
        # 校验必须知道页面是 fixed 还是 flex：flex 页的 slot_id 是块自己的 id，
        # 拿固定布局的槽位表去比对会把每个块都判成「布局没有这个槽位」
        slide = Slide(
            id=state["slide_id"],
            layout_id=state["layout_id"],
            layout_mode=state.get("layout_mode") or "fixed",
            layout_tree=state.get("layout_tree"),
            blocks=patched,
        )
        return {
            "operations": filtered.accepted,
            "discarded": filtered.discarded,
            "patched_blocks": patched,
            "issues": validate_slide(
                slide,
                theme=resolve_theme(
                    state.get("theme_id") or "ivory", state.get("theme_overrides")
                ),
            ),
        }

    async def repair(state: SlideEditWorkflowState) -> dict:
        messages = [_describe(issue) for issue in state["issues"]]
        repaired = state["input"].model_copy(update={"issues": messages})
        return {"input": repaired, "repairs": state.get("repairs", 0) + 1}

    def route(state: SlideEditWorkflowState) -> str:
        # 结构错误与容量超限都先尝试修一轮；修完后 warning 可放行，error 则失败
        if not state["issues"]:
            return END
        if state.get("repairs", 0) >= MAX_REPAIR_ROUNDS:
            return END
        return "repair"

    graph = StateGraph(SlideEditWorkflowState)
    graph.add_node("generate", generate)
    graph.add_node("check", check)
    graph.add_node("repair", repair)
    graph.add_edge(START, "generate")
    graph.add_edge("generate", "check")
    graph.add_conditional_edges("check", route, {"repair": "repair", END: END})
    graph.add_edge("repair", "generate")
    return graph.compile()


async def run_slide_edit_workflow(
    workflow,
    *,
    payload: SlideEditInput,
    slide_id: str,
    layout_id: str,
    blocks: list[Block],
    layout_mode: str = "fixed",
    layout_tree: FlexContainer | None = None,
    theme_id: str | None = None,
    theme_overrides: dict[str, Any] | None = None,
) -> tuple[list[BlockPatch], list[DiscardedPatch], list[StructureIssue], list[Block]]:
    result = await workflow.ainvoke(
        {
            "input": payload,
            "slide_id": slide_id,
            "layout_id": layout_id,
            "layout_mode": layout_mode,
            "layout_tree": layout_tree,
            "theme_id": theme_id or "ivory",
            "theme_overrides": theme_overrides or {},
            "original_blocks": blocks,
            "repairs": 0,
        }
    )
    operations = list(result.get("operations") or [])
    discarded = list(result.get("discarded") or [])
    issues = list(result.get("issues") or [])
    patched = list(result.get("patched_blocks") or [])

    if has_blocking_issue(issues):
        raise InvalidSlideEditOutputError(
            "局部修改后页面结构仍不合法："
            + "；".join(_describe(issue) for issue in issues if issue.severity == "error")
        )
    return operations, discarded, issues, patched


def parse_slide_blocks(raw: list[dict]) -> list[Block]:
    return _blocks_adapter.validate_python(raw)


def _describe(issue: StructureIssue) -> str:
    scope = f"槽位 {issue.slot_id}" if issue.slot_id else "本页"
    return f"{scope}：{issue.message}"
