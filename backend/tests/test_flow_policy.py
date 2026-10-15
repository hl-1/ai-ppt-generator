import uuid

import pytest

from app.domain.content import DiagramBlock, DiagramEdge, DiagramNode, Slide
from app.domain.flow_policy import enforce_text_flow_policy, should_keep_flow_diagram
from app.domain.slide_draft import DiagramContent, SlideDraft, draft_to_slide


def graph(pairs, **updates):
    return DiagramBlock(
        id="graph",
        slot_id="body",
        diagram_type="flow",
        nodes=[DiagramNode(id=n, title=f"步骤 {n}", desc="完整说明" * 20) for n in "abcd"],
        edges=[DiagramEdge(source=s, target=t) for s, t in pairs],
        **updates,
    )


@pytest.mark.parametrize(
    "context",
    [
        "先采集，然后校验，最后发布",
        "故障预警、决策、审批、成功与失败",
        "如果通过就发布，否则退回",
    ],
)
def test_linear_graph_is_always_rejected_even_with_complex_keywords(context):
    block = graph([("a", "b"), ("b", "c"), ("c", "d")])
    assert not should_keep_flow_diagram(block.nodes, block.edges, context=[context])


@pytest.mark.parametrize(
    ("pairs", "context"),
    [
        ([("a", "b"), ("b", "c"), ("b", "d")], "先采集，再判断是否通过，通过则发布，否则退回"),
        ([("a", "b"), ("a", "c"), ("b", "d"), ("c", "d")], "并行执行两个校验，完成后合并结果"),
        ([("a", "b"), ("b", "c"), ("c", "d"), ("d", "a")], "校验失败时返回开始重新执行"),
    ],
)
def test_real_nonlinear_relations_are_preserved(pairs, context):
    block = graph(pairs)
    assert should_keep_flow_diagram(block.nodes, block.edges, context=[context])
    slide = Slide(id="s", layout_id="bullets", blocks=[block])
    assert enforce_text_flow_policy(slide, context=[context]).blocks[0] == block


@pytest.mark.parametrize(
    "pairs",
    [
        [("a", "b"), ("a", "b"), ("b", "c"), ("c", "d")],
        [("a", "b"), ("a", "c")],
        [("a", "b"), ("b", "c"), ("c", "missing")],
    ],
)
def test_duplicates_disconnected_nodes_and_invalid_references_do_not_count_as_complexity(pairs):
    block = graph(pairs)
    assert not should_keep_flow_diagram(block.nodes, block.edges)


def test_generated_branch_cannot_use_its_own_labels_as_source_evidence():
    block = graph([("a", "b"), ("b", "c"), ("b", "d")])
    block.edges[1].label = "如果成功则继续"
    slide = Slide(id="s", layout_id="bullets", blocks=[block])
    result = enforce_text_flow_policy(
        slide, context=["凭证有效期5分钟，决策上限12次，任务状态持久化"]
    )
    steps = result.blocks[0]
    assert steps.type == "bullets"
    assert steps.id == block.id and steps.slot_id == block.slot_id
    assert len(steps.items) == len(block.nodes)
    assert all(
        node.title in item and node.desc in item
        for node, item in zip(block.nodes, steps.items, strict=True)
    )


def test_concurrency_budget_is_not_evidence_of_parallel_execution():
    block = graph([("a", "b"), ("a", "c"), ("b", "d"), ("c", "d")])
    assert not should_keep_flow_diagram(
        block.nodes,
        block.edges,
        context=[
            "决策上限12次，每用户默认并发1个执行任务，执行失败记入任务状态。",
        ],
    )


def test_fixed_draft_also_rejects_linear_mermaid_without_truncating_nodes():
    nodes = [DiagramNode(id=f"n{i}", title=f"步骤 {i}", desc="长说明" * 30) for i in range(10)]
    draft = SlideDraft(
        blocks=[
            DiagramContent(
                slot_id="body",
                diagram_type="flow",
                nodes=[n.model_dump() for n in nodes],
                edges=[
                    {"source": a.id, "target": b.id} for a, b in zip(nodes, nodes[1:], strict=False)
                ],
                mermaid="flowchart TB\n n0 --> n1",
            )
        ]
    )
    steps = draft_to_slide(uuid.uuid4(), "bullets", draft).blocks[0]
    assert steps.type == "bullets" and len(steps.items) == 10
    assert all(node.desc in item for node, item in zip(nodes, steps.items, strict=True))
