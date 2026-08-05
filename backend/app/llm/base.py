from typing import Literal, Protocol

from pydantic import BaseModel, Field

from app.domain.outline import OutlineDraft
from app.domain.slide_draft import SlideDraft
from app.domain.slide_patch import BlockPatch


class OutlineSourceSection(BaseModel):
    """带稳定引用编号的来源小节。

    ref 采用「来源编号:小节编号」（如 S1:2），生成结果只能引用这些编号，
    才能在后续正文生成时追溯到真实输入。
    """

    ref: str = Field(min_length=1, max_length=32)
    heading: str | None = None
    level: int = Field(ge=0, le=6)
    text: str
    locator: str


class OutlineGenerationInput(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    audience: str | None = Field(default=None, max_length=100)
    tone: str = Field(min_length=1, max_length=32)
    # 与产品页数区间对齐；工作流层不再二次放宽，避免模型按任意页数胡编
    page_count: int = Field(ge=1, le=20)
    sections: list[OutlineSourceSection] = Field(default_factory=list)


class OutlineGenerator(Protocol):
    async def generate(self, payload: OutlineGenerationInput) -> OutlineDraft:
        """根据项目参数与来源小节生成大纲草稿。"""


class SlideGenerationInput(BaseModel):
    """单页正文生成的输入。

    只带这一页需要的上下文：整份 PPT 的基调、本页在大纲里的定位，
    以及本页引用到的来源片段。页面之间因此互不依赖，可以并发生成。
    """

    deck_title: str
    audience: str | None = None
    tone: str
    position: int = Field(ge=1)
    total_pages: int = Field(ge=1)

    page_title: str
    objective: str
    key_points: list[str]
    layout_id: str
    sections: list[OutlineSourceSection] = Field(default_factory=list)
    # 相邻页标题，用来避免内容重复或衔接断裂
    neighbor_titles: list[str] = Field(default_factory=list)
    # 修复轮次带上上一轮的结构问题，让模型定向改而不是从头重来
    issues: list[str] = Field(default_factory=list)


class SlideGenerator(Protocol):
    async def generate(self, payload: SlideGenerationInput) -> SlideDraft:
        """根据大纲页与布局槽位生成单页正文草稿。"""


SlideEditAction = Literal["rewrite", "condense", "expand"]


class SlideEditBlockInput(BaseModel):
    """发给模型的可改块快照：不含 locked，也不含 image/chart。"""

    block_id: str
    slot_id: str
    type: Literal["text", "bullets", "kpi", "table"]
    text: str | None = None
    items: list[str] | None = None
    value: str | None = None
    label: str | None = None
    note: str | None = None
    header: list[str] | None = None
    rows: list[list[str]] | None = None


class SlideEditInput(BaseModel):
    """单页 AI 局部修改的输入。

    只带当前页未锁定的可写块与槽位容量，模型返回块级操作清单，
    而不是整页重写。
    """

    deck_title: str
    audience: str | None = None
    tone: str
    page_title: str
    layout_id: str
    action: SlideEditAction
    instruction: str | None = None
    blocks: list[SlideEditBlockInput] = Field(default_factory=list)
    # 修复轮次带上上一轮的结构问题，让模型定向改而不是从头重来
    issues: list[str] = Field(default_factory=list)


class SlideEditGenerator(Protocol):
    async def generate(self, payload: SlideEditInput) -> list[BlockPatch]:
        """根据动作与当前可改块生成块级操作清单。"""
