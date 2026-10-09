import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.domain.outline import DeckBlueprint, OutlinePage

OutlineStatus = Literal["generating", "draft", "confirmed", "failed", "cancelled"]
OutlineStage = Literal[
    "queue", "load_input", "travel_research", "plan_structure", "validate", "save"
]
OutlineStageStatus = Literal[
    "pending", "started", "succeeded", "partial", "retrying", "failed", "cancelled"
]
OutlineErrorCode = Literal[
    "queue_unavailable",
    "input_load_failed",
    "input_missing",
    "travel_research_failed",
    "travel_timeout",
    "llm_not_configured",
    "model_timeout",
    "model_unavailable",
    "model_auth_failed",
    "model_rate_limited",
    "model_request_rejected",
    "invalid_model_output",
    "invalid_outline",
    "save_failed",
    "unknown",
]


class OutlineIssue(BaseModel):
    code: str
    message: str
    action: str
    service: str | None = None


class OutlineFailure(OutlineIssue):
    stage: OutlineStage
    retryable: bool = True


class OutlineStageExecution(BaseModel):
    stage: OutlineStage
    status: OutlineStageStatus = "pending"
    message: str = "等待执行"
    started_at: datetime | None = None
    finished_at: datetime | None = None
    attempt: int = 1
    error_code: OutlineErrorCode | None = None
    issues: list[OutlineIssue] = Field(default_factory=list)


class OutlineHistoryEntry(BaseModel):
    timestamp: datetime
    stage: OutlineStage | None = None
    status: OutlineStageStatus | None = None
    message: str
    attempt: int = 1
    error_code: OutlineErrorCode | None = None


class OutlineExecution(BaseModel):
    job_id: str
    status: OutlineStatus = "generating"
    stage: OutlineStage = "queue"
    started_at: datetime
    updated_at: datetime
    finished_at: datetime | None = None
    attempt: int = 1
    max_attempts: int = 2
    retry_at: datetime | None = None
    failure: OutlineFailure | None = None
    stages: list[OutlineStageExecution]
    history: list[OutlineHistoryEntry] = Field(default_factory=list)


class OutlinePublic(BaseModel):
    blueprint: DeckBlueprint = Field(default_factory=DeckBlueprint)
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    status: OutlineStatus
    pages: list[OutlinePage]
    revision: int
    job_id: str | None
    execution: OutlineExecution | None = None
    error_code: OutlineErrorCode | None
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
    type: Literal["snapshot", "progress", "completed", "failed", "cancelled"]
    status: OutlineStatus
    progress: int = Field(ge=0, le=100)
    message: str
    revision: int | None = None
    stage: OutlineStage | None = None
    stage_status: OutlineStageStatus | None = None
    error_code: OutlineErrorCode | None = None
    job_id: str | None = None
    timestamp: datetime | None = None
    attempt: int = 1
    max_attempts: int = 2
    retry_at: datetime | None = None
    issues: list[OutlineIssue] = Field(default_factory=list)
    execution: OutlineExecution | None = None
