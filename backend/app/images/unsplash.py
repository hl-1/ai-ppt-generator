import logging

import httpx

from app.domain.content import ImageSource
from app.images.base import ImageAsset, ImageRequest

logger = logging.getLogger(__name__)

API_BASE = "https://api.unsplash.com"


class UnsplashImageProvider:
    """Unsplash 图库检索。

    Unsplash 的接入条款要求：使用图片时标注作者，并在实际取用时回调
    download_location。这两件事都不能省，否则属于违规使用。
    """

    source: ImageSource = "stock"

    def __init__(
        self,
        *,
        client: httpx.AsyncClient,
        access_key: str,
        timeout_seconds: float = 30,
    ) -> None:
        self._client = client
        self._access_key = access_key
        self._timeout = timeout_seconds

    def available(self) -> bool:
        return bool(self._access_key.strip())

    async def fetch(self, request: ImageRequest) -> ImageAsset | None:
        if not self.available():
            return None

        headers = {"Authorization": f"Client-ID {self._access_key}"}
        try:
            search = await self._client.get(
                f"{API_BASE}/search/photos",
                headers=headers,
                params={
                    "query": request.query,
                    "per_page": 1,
                    "orientation": _orientation(request.aspect_ratio),
                    "content_filter": "high",
                },
                timeout=self._timeout,
            )
            search.raise_for_status()
            results = search.json().get("results") or []
            if not results:
                return None

            photo = results[0]
            image = await self._client.get(
                photo["urls"]["regular"],
                timeout=self._timeout,
            )
            image.raise_for_status()
            await self._track_download(photo, headers)
        except (httpx.HTTPError, ValueError, KeyError) as error:
            logger.warning("图库检索失败，降级到占位图：%s", error)
            return None

        return ImageAsset(
            data=image.content,
            content_type=image.headers.get("content-type", "image/jpeg"),
            source="stock",
            credit=_credit(photo),
        )

    async def _track_download(self, photo: dict, headers: dict[str, str]) -> None:
        location = (photo.get("links") or {}).get("download_location")
        if not location:
            return
        try:
            await self._client.get(location, headers=headers, timeout=self._timeout)
        except httpx.HTTPError as error:
            # 回调失败不影响本次配图，仅记录
            logger.warning("Unsplash 下载回调失败：%s", error)


def _orientation(aspect_ratio: float) -> str:
    if aspect_ratio >= 1.2:
        return "landscape"
    if aspect_ratio <= 0.85:
        return "portrait"
    return "squarish"


def _credit(photo: dict) -> str:
    name = ((photo.get("user") or {}).get("name")) or "Unsplash"
    return f"Photo by {name} on Unsplash"
