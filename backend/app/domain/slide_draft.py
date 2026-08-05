import uuid
from typing import Annotated, Literal

from pydantic import BaseModel, Field

from app.domain.content import (
    BulletsBlock,
    ChartBlock,
    ChartKind,
    ChartSeries,
    ImageBlock,
    KpiBlock,
    Slide,
    TableBlock,
    TextBlock,
)

# 模型只负责"往哪个槽位放什么内容"。块 id、锁定标记、图片来源这些
# 由服务端掌握的字段不进入模型契约：让模型编造它们只会带来无谓的校验负担。


class SlotContentBase(BaseModel):
    slot_id: str


class TextContent(SlotContentBase):
    type: Literal["text"] = "text"
    text: str


class BulletsContent(SlotContentBase):
    type: Literal["bullets"] = "bullets"
    items: list[str] = Field(min_length=1)


class ImageContent(SlotContentBase):
    type: Literal["image"] = "image"
    # 首版没有真实图源，模型只描述"这里该是什么图"，由图片节点后续填充
    alt: str


class ChartSeriesContent(BaseModel):
    name: str
    values: list[float] = Field(min_length=1)


class ChartContent(SlotContentBase):
    type: Literal["chart"] = "chart"
    chart_type: ChartKind
    categories: list[str] = Field(min_length=1)
    series: list[ChartSeriesContent] = Field(min_length=1)
    unit: str | None = None


class TableContent(SlotContentBase):
    type: Literal["table"] = "table"
    header: list[str] = Field(min_length=1)
    rows: list[list[str]] = Field(min_length=1)


class KpiContent(SlotContentBase):
    type: Literal["kpi"] = "kpi"
    value: str
    label: str
    note: str | None = None


SlotContent = Annotated[
    TextContent | BulletsContent | ImageContent | ChartContent | TableContent | KpiContent,
    Field(discriminator="type"),
]


class SlideDraft(BaseModel):
    blocks: list[SlotContent] = Field(min_length=1)
    speaker_notes: str | None = None


def draft_to_slide(slide_id: uuid.UUID, layout_id: str, draft: SlideDraft) -> Slide:
    """把模型产出的槽位内容补齐为完整内容块。"""
    blocks = [_to_block(f"{slide_id}-{content.slot_id}", content) for content in draft.blocks]
    return Slide(
        id=str(slide_id),
        layout_id=layout_id,
        blocks=blocks,
        speaker_notes=draft.speaker_notes,
    )


def _to_block(block_id: str, content: SlotContent):  # noqa: ANN202
    common = {"id": block_id, "slot_id": content.slot_id}
    match content:
        case TextContent():
            return TextBlock(**common, text=content.text)
        case BulletsContent():
            return BulletsBlock(**common, items=content.items)
        case ImageContent():
            # 没有图源时统一走占位图：图片获取失败不应阻断整页内容
            return ImageBlock(**common, alt=content.alt, source="placeholder")
        case ChartContent():
            return ChartBlock(
                **common,
                chart_type=content.chart_type,
                categories=content.categories,
                series=[ChartSeries(name=s.name, values=s.values) for s in content.series],
                unit=content.unit,
            )
        case TableContent():
            return TableBlock(**common, header=content.header, rows=content.rows)
        case KpiContent():
            return KpiBlock(**common, value=content.value, label=content.label, note=content.note)
