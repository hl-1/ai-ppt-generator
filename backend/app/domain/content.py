from typing import Annotated, Literal

from pydantic import BaseModel, Field

BlockType = Literal["text", "bullets", "image", "chart", "table", "kpi"]
ImageSource = Literal["generated", "stock", "upload", "placeholder"]
ChartKind = Literal["bar", "column", "line", "pie"]


class BlockBase(BaseModel):
    id: str
    slot_id: str
    # 人工编辑过的内容默认受保护，AI 局部修改必须绕开它
    locked: bool = False


class TextBlock(BlockBase):
    type: Literal["text"] = "text"
    text: str


class BulletsBlock(BlockBase):
    type: Literal["bullets"] = "bullets"
    items: list[str]


class ImageBlock(BlockBase):
    type: Literal["image"] = "image"
    # source 为 placeholder 时没有真实图源，两端各自按主题色绘制几何占位图。
    # 这条降级路径保证图片获取失败不会阻断整份文稿。
    url: str | None = None
    # 可访问性要求图片必须有替代文本，因此不设默认空值
    alt: str
    source: ImageSource


class ChartSeries(BaseModel):
    name: str
    values: list[float]


class ChartBlock(BlockBase):
    type: Literal["chart"] = "chart"
    chart_type: ChartKind
    categories: list[str]
    series: list[ChartSeries]
    unit: str | None = None


class TableBlock(BlockBase):
    type: Literal["table"] = "table"
    header: list[str]
    rows: list[list[str]]


class KpiBlock(BlockBase):
    type: Literal["kpi"] = "kpi"
    value: str
    label: str
    note: str | None = None


Block = Annotated[
    TextBlock | BulletsBlock | ImageBlock | ChartBlock | TableBlock | KpiBlock,
    Field(discriminator="type"),
]


class Slide(BaseModel):
    id: str
    layout_id: str
    blocks: list[Block]
    speaker_notes: str | None = None
    # 乐观锁版本号：AI 修改提交时带上它，不一致即判定冲突而非后写覆盖
    revision: int = 1


class Deck(BaseModel):
    """PPT 的统一内容模型。

    内容、布局、主题三者分离：这里只描述"有什么内容、放在哪个槽位"，
    槽位几何来自布局，视觉表现来自主题。
    """

    id: str
    title: str
    theme_id: str
    slides: list[Slide]

    def slide_by_id(self, slide_id: str) -> Slide | None:
        return next((slide for slide in self.slides if slide.id == slide_id), None)
