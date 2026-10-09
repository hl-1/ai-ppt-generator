from typing import Literal

from pydantic import BaseModel, Field

from app.images.base import ImageCandidate


class ImageSearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=120)
    aspect_ratio: float = Field(default=1.777, gt=0, le=10)


class ImageSearchPublic(BaseModel):
    search_id: str
    candidates: list[ImageCandidate]
    queries: list[str]


class ImageApplyRequest(BaseModel):
    revision: int
    search_id: str = Field(min_length=1, max_length=64)
    candidate_id: str = Field(min_length=1, max_length=100)


class ImageGenerateRequest(BaseModel):
    revision: int
    query: str = Field(default="", max_length=120)
    source: Literal["auto", "stock", "generated"] = "auto"


class ImageLockRequest(BaseModel):
    revision: int
    locked: bool


class ImageAddRequest(BaseModel):
    revision: int
    subject: str = Field(default="配图", min_length=1, max_length=120)
