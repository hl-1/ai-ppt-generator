import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.ingest.models import SourceSection

Tone = Literal["professional", "plain", "punchy"]
ProjectStatus = Literal["draft", "outline_ready", "generating", "ready"]
SourceKind = Literal["topic", "text", "document"]

# 页数范围与文档给出的推荐区间一致：太少不成篇，太多单次生成不可控
MIN_PAGE_COUNT = 5
MAX_PAGE_COUNT = 20


class ProjectCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    audience: str | None = Field(default=None, max_length=100)
    tone: Tone = "professional"
    page_count: int = Field(default=10, ge=MIN_PAGE_COUNT, le=MAX_PAGE_COUNT)
    theme_id: str = Field(default="ivory", max_length=50)


class ProjectUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    audience: str | None = Field(default=None, max_length=100)
    tone: Tone | None = None
    page_count: int | None = Field(default=None, ge=MIN_PAGE_COUNT, le=MAX_PAGE_COUNT)
    theme_id: str | None = Field(default=None, max_length=50)


class SourcePublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    kind: SourceKind
    filename: str | None
    content_type: str | None
    size_bytes: int | None
    sections: list[SourceSection]
    warnings: list[str]
    char_count: int
    created_at: datetime


class ProjectPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    audience: str | None
    tone: Tone
    page_count: int
    theme_id: str
    status: ProjectStatus
    created_at: datetime
    updated_at: datetime


class ProjectDetail(ProjectPublic):
    sources: list[SourcePublic]


class TextSourceCreate(BaseModel):
    kind: Literal["topic", "text"]
    content: str = Field(min_length=1, max_length=200_000)
