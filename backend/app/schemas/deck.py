import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.domain.content import Block
from app.domain.validation import StructureIssue

SlideStatus = Literal["pending", "generating", "ready", "failed"]
# idle 表示还没生成过；partial 表示有页未就绪且当前没有任务在跑，可逐页重试。
# 取消不单列状态：取消后剩下的就是「部分完成」，多一个状态只会让前端多分支。
DeckStatus = Literal["idle", "generating", "ready", "partial"]


class SlidePublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    outline_page_id: uuid.UUID
    position: int
    layout_id: str
    title: str
    status: SlideStatus
    blocks: list[Block]
    speaker_notes: str | None
    issues: list[StructureIssue]
    error: str | None
    revision: int
    updated_at: datetime


class DeckPublic(BaseModel):
    project_id: uuid.UUID
    title: str
    theme_id: str
    status: DeckStatus
    total: int
    ready: int
    failed: int
    slides: list[SlidePublic]


class DeckGenerateRequest(BaseModel):
    # 默认续跑：已就绪的页不会白白重来一遍，这也是断点恢复的入口
    regenerate_all: bool = False


class DeckGenerateAccepted(BaseModel):
    job_id: str
    status: Literal["generating"] = "generating"
    total: int
    pending: int


class DeckEvent(BaseModel):
    type: Literal[
        "snapshot",
        "slide_started",
        "slide_completed",
        "slide_failed",
        "completed",
        "cancelled",
        "failed",
    ]
    status: DeckStatus
    progress: int = Field(ge=0, le=100)
    message: str
    slide_id: uuid.UUID | None = None
    position: int | None = None
    ready: int = 0
    failed: int = 0
    total: int = 0
