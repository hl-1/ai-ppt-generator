from typing import Protocol

from pydantic import BaseModel, Field

from app.domain.outline import OutlineDraft


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
