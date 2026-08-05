import uuid

from pydantic import BaseModel, Field


class OutlinePageDraft(BaseModel):
    title: str = Field(min_length=1, max_length=100)
    objective: str = Field(min_length=1, max_length=300)
    key_points: list[str] = Field(min_length=2, max_length=5)
    # 格式为「来源编号:小节编号」，例如 S1:2。服务端会校验引用确实存在，
    # 避免模型编造一个无法追溯的来源。
    source_refs: list[str] = Field(default_factory=list, max_length=10)
    layout_id: str


class OutlineDraft(BaseModel):
    pages: list[OutlinePageDraft]


class OutlinePage(OutlinePageDraft):
    id: uuid.UUID = Field(default_factory=uuid.uuid4)


class OutlinePlan(BaseModel):
    pages: list[OutlinePage]
