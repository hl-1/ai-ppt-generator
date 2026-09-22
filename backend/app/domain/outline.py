import uuid
from typing import Literal

from pydantic import BaseModel, Field


class ReportBrief(BaseModel):
    scenario: Literal["general", "business_review", "project_review", "proposal", "strategy"] = (
        "general"
    )
    goal: str = Field(default="", max_length=500)
    decision_request: str = Field(default="", max_length=300)


class DeckBlueprint(BaseModel):
    core_message: str = Field(default="", max_length=300)
    narrative: list[str] = Field(default_factory=list, max_length=12)
    decision_request: str = Field(default="", max_length=300)


class EvidenceItem(BaseModel):
    """来源原句与数据口径；仅表示可追溯性，不代表来源已获独立核实。"""

    source_ref: str = Field(min_length=1, max_length=32)
    quote: str = Field(min_length=1, max_length=500)
    metric: str = Field(default="", max_length=80)
    category: str = Field(default="", max_length=80)
    value: str = Field(default="", max_length=32)
    unit: str = Field(default="", max_length=32)
    period: str = Field(default="", max_length=40)
    scope: str = Field(default="", max_length=100)


PageRole = Literal["cover", "toc", "section", "content", "summary"]
# 企业汇报里的页面职责：页型描述“长什么样”，叙事角色描述“为什么存在”。
NarrativeRole = Literal[
    "cover",
    "executive_summary",
    "performance",
    "driver",
    "risk",
    "action",
    "decision",
    "supporting",
    "summary",
]
EvidenceKind = Literal[
    "narrative",
    "kpi",
    "trend",
    "comparison",
    "composition",
    "timeline",
    "flow",
    "actions",
    "table",
    "chart",
    "waterfall",
]
VisualType = Literal[
    "auto",
    "line",
    "column",
    "bar",
    "pie",
    "flow",
    "timeline",
    "financial_table",
    "waterfall",
    "combo_chart",
]


class OutlinePageDraft(BaseModel):
    title: str = Field(min_length=1, max_length=100)
    objective: str = Field(min_length=1, max_length=300)
    key_points: list[str] = Field(min_length=2, max_length=5)
    # 格式为「来源编号:小节编号」，例如 S1:2。服务端会校验引用确实存在，
    # 避免模型编造一个无法追溯的来源。
    source_refs: list[str] = Field(default_factory=list, max_length=10)
    layout_id: str
    page_role: PageRole = "content"
    # 企业汇报的叙事职责与证据形态，供页面选择和质量检查使用。
    narrative_role: NarrativeRole = "supporting"
    evidence_kind: EvidenceKind = "narrative"
    # 具体视觉类型由大纲建议，服务端仍会结合已验证证据做最终选择。
    visual_type: VisualType = "auto"
    key_message: str = Field(default="", max_length=200)
    evidence: list[EvidenceItem] = Field(default_factory=list, max_length=12)
    planning_notes: list[str] = Field(default_factory=list, max_length=16)
    # 一句配图意图，为空表示这页不配图。放在大纲阶段而不是正文阶段，
    # 是因为「哪些页该配图」是全局节奏问题：正文页各自并发生成，看不到彼此。
    visual: str | None = Field(default=None, max_length=120)


class OutlineDraft(BaseModel):
    pages: list[OutlinePageDraft]
    blueprint: DeckBlueprint = Field(default_factory=DeckBlueprint)


class OutlinePage(OutlinePageDraft):
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
