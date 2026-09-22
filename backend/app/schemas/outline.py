import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.domain.outline import DeckBlueprint, OutlinePage

OutlineStatus = Literal["generating", "draft", "confirmed", "failed"]


class OutlinePublic(BaseModel):
    blueprint: DeckBlueprint = Field(default_factory=DeckBlueprint)
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    status: OutlineStatus
    pages: list[OutlinePage]
    revision: int
    job_id: str | None
    error: str | None
    created_at: datetime
    updated_at: datetime


class OutlineGenerateAccepted(BaseModel):
    job_id: str
    status: Literal["generating"] = "generating"


class OutlineUpdate(BaseModel):
    blueprint: DeckBlueprint | None = None
    revision: int = Field(ge=1)
    pages: list[OutlinePage] = Field(min_length=1, max_length=20)


class OutlinePageEvidenceFitRequest(BaseModel):
    revision: int = Field(ge=1)
    evidence_kind: Literal["trend", "chart"]
    visual_type: Literal[
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
    ] = "auto"


class OutlineRevisionRequest(BaseModel):
    revision: int = Field(ge=1)


class OutlineEvent(BaseModel):
    type: Literal["snapshot", "progress", "completed", "failed"]
    status: OutlineStatus
    progress: int = Field(ge=0, le=100)
    message: str
    revision: int | None = None
