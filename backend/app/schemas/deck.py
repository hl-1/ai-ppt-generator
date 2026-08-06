import uuid
from datetime import datetime
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.domain.content import Block
from app.domain.slide_patch import BlockPatch
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


class TextBlockUpdate(BaseModel):
    type: Literal["text"]
    revision: int
    text: str


class BulletsBlockUpdate(BaseModel):
    type: Literal["bullets"]
    revision: int
    items: list[str]


class KpiBlockUpdate(BaseModel):
    type: Literal["kpi"]
    revision: int
    value: str
    label: str
    note: str | None = None


class TableBlockUpdate(BaseModel):
    type: Literal["table"]
    revision: int
    header: list[str]
    rows: list[list[str]]


BlockUpdate = Annotated[
    TextBlockUpdate | BulletsBlockUpdate | KpiBlockUpdate | TableBlockUpdate,
    Field(discriminator="type"),
]


class SlideOrderRequest(BaseModel):
    slide_ids: list[uuid.UUID]


class LayoutSwitchRequest(BaseModel):
    layout_id: str
    revision: int


class LayoutCandidatePublic(BaseModel):
    layout_id: str
    name: str
    usage: str
    compatible: bool
    reason: str | None = None
    current: bool = False


AiEditAction = Literal["rewrite", "condense", "expand", "instruct"]


class AiEditRequest(BaseModel):
    action: AiEditAction = "instruct"
    instruction: str | None = Field(default=None, max_length=500)
    revision: int

    @model_validator(mode="after")
    def require_instruction_for_instruct(self) -> Self:
        # 对话指令模式必须带有效 instruction；旧三动作仍可无指令调用
        if self.action == "instruct":
            text = (self.instruction or "").strip()
            if not text:
                raise ValueError("对话修改必须提供 instruction")
            self.instruction = text
        return self


class AiEditOperationPublic(BaseModel):
    block_id: str
    slot_id: str
    type: Literal["text", "bullets", "kpi", "table"]
    before: BlockPatch
    after: BlockPatch


class DiscardedOperationPublic(BaseModel):
    block_id: str
    reason: str


class AiEditProposalPublic(BaseModel):
    revision: int
    operations: list[AiEditOperationPublic]
    discarded: list[DiscardedOperationPublic]
    warnings: list[StructureIssue]


class AiEditApplyRequest(BaseModel):
    revision: int
    operations: list[BlockPatch]
