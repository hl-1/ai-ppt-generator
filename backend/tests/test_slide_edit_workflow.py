import pytest

from app.domain.content import BulletsBlock, TextBlock
from app.domain.slide_patch import BulletsPatch, TextPatch
from app.llm.base import SlideEditInput
from app.workflows.slide_edit import build_slide_edit_workflow, run_slide_edit_workflow


def _blocks() -> list[TextBlock | BulletsBlock]:
    return [
        TextBlock(id="t1", slot_id="title", text="现状与问题", locked=False),
        BulletsBlock(
            id="b1",
            slot_id="body",
            items=["交付慢", "重复建设"],
            locked=False,
        ),
    ]


def _payload(**overrides) -> SlideEditInput:
    base = {
        "deck_title": "平台化复盘",
        "tone": "professional",
        "page_title": "现状与问题",
        "layout_id": "bullets",
        "action": "condense",
        "blocks": [
            {
                "block_id": "t1",
                "slot_id": "title",
                "type": "text",
                "text": "现状与问题",
            },
            {
                "block_id": "b1",
                "slot_id": "body",
                "type": "bullets",
                "items": ["交付慢", "重复建设"],
            },
        ],
    }
    return SlideEditInput(**{**base, **overrides})


class ScriptedEditGenerator:
    def __init__(self, batches: list[list]) -> None:
        self._batches = batches
        self.prompts: list[list[str]] = []

    async def generate(self, payload: SlideEditInput):
        self.prompts.append(list(payload.issues))
        return self._batches[min(len(self.prompts) - 1, len(self._batches) - 1)]


@pytest.mark.asyncio
async def test_workflow_repairs_capacity_overflow_once() -> None:
    too_long = ["超出容量的要点" * 12] * 9
    generator = ScriptedEditGenerator(
        [
            [BulletsPatch(block_id="b1", items=too_long)],
            [BulletsPatch(block_id="b1", items=["精简要点一", "精简要点二"])],
        ]
    )
    workflow = build_slide_edit_workflow(generator)

    operations, discarded, issues, patched = await run_slide_edit_workflow(
        workflow,
        payload=_payload(),
        slide_id="slide-1",
        layout_id="bullets",
        blocks=_blocks(),
    )

    assert generator.prompts[0] == []
    assert generator.prompts[1]
    assert discarded == []
    assert issues == []
    assert operations[0].items == ["精简要点一", "精简要点二"]
    assert patched[1].items == ["精简要点一", "精简要点二"]


@pytest.mark.asyncio
async def test_workflow_keeps_warnings_after_one_repair() -> None:
    too_long = ["超出容量的要点" * 12] * 9
    generator = ScriptedEditGenerator([[BulletsPatch(block_id="b1", items=too_long)]])
    workflow = build_slide_edit_workflow(generator)

    _, _, issues, _ = await run_slide_edit_workflow(
        workflow,
        payload=_payload(),
        slide_id="slide-1",
        layout_id="bullets",
        blocks=_blocks(),
    )

    assert len(generator.prompts) == 2
    assert issues
    assert all(issue.severity == "warning" for issue in issues)


@pytest.mark.asyncio
async def test_workflow_filters_locked_ops() -> None:
    blocks = [
        TextBlock(id="t1", slot_id="title", text="标题", locked=True),
        BulletsBlock(id="b1", slot_id="body", items=["要点"], locked=False),
    ]
    generator = ScriptedEditGenerator(
        [
            [
                TextPatch(block_id="t1", text="不应生效"),
                BulletsPatch(block_id="b1", items=["新要点"]),
            ]
        ]
    )
    workflow = build_slide_edit_workflow(generator)

    operations, discarded, _, patched = await run_slide_edit_workflow(
        workflow,
        payload=_payload(
            blocks=[
                {
                    "block_id": "b1",
                    "slot_id": "body",
                    "type": "bullets",
                    "items": ["要点"],
                }
            ]
        ),
        slide_id="slide-1",
        layout_id="bullets",
        blocks=blocks,
    )

    assert [op.block_id for op in operations] == ["b1"]
    assert any("人工修改" in item.reason for item in discarded)
    assert patched[0].text == "标题"
    assert patched[1].items == ["新要点"]
