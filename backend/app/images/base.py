from typing import Literal, Protocol

from pydantic import BaseModel, Field

from app.domain.content import ImageSource


class ImageRequest(BaseModel):
    """一次配图需求。

    prompt 面向生图模型，query 面向图库检索：同一段描述在两边的
    最佳表达并不一样，硬用一份会让其中一边效果明显变差。
    """

    prompt: str
    query: str
    # 槽位宽高比，供应商据此挑选最接近的可用尺寸，减少后续裁切损失
    aspect_ratio: float
    queries: list[str] = Field(default_factory=list)
    subject: str = ""
    preferred_source: Literal["auto", "stock", "generated"] = "auto"
    require_real: bool = False
    excluded_ids: set[str] = Field(default_factory=set)


class ImageAsset(BaseModel):
    data: bytes
    content_type: str
    source: ImageSource
    # 图库通常要求标注作者，这条信息必须随图片一起保存
    credit: str | None = None
    credit_url: str | None = None
    asset_id: str | None = None


class ImageCandidate(BaseModel):
    id: str
    url: str
    thumbnail_url: str
    description: str = ""
    width: int = 0
    height: int = 0
    credit: str
    credit_url: str
    author_url: str = ""
    download_location: str | None = None
    match_reason: str = "待人工确认主体"
    metadata_matched: bool = False


class ImageProvider(Protocol):
    source: ImageSource

    def available(self) -> bool:
        """未配置凭证时返回 False，让调用方直接跳到下一级。"""

    async def fetch(self, request: ImageRequest) -> ImageAsset | None:
        """取不到返回 None；可向 pipeline 抛出不含凭证的 ImageFetchError。"""
