import httpx

from app.core.config import get_settings
from app.images.base import ImageAsset, ImageProvider, ImageRequest
from app.images.generated import GeneratedImageProvider
from app.images.unsplash import UnsplashImageProvider


class ImagePipeline:
    """按优先级依次尝试图源，全部失败则返回 None 交给占位图。

    顺序是「生图 → 图库」：生图能精确贴合页面语义，图库胜在稳定与真实，
    因此把它放在后面兜底。两级都不可用时不报错，占位图本身就是设计的一部分。
    """

    def __init__(self, providers: list[ImageProvider]) -> None:
        self._providers = providers

    @property
    def enabled(self) -> bool:
        return any(provider.available() for provider in self._providers)

    async def fetch(self, request: ImageRequest) -> ImageAsset | None:
        for provider in self._providers:
            if not provider.available():
                continue
            asset = await provider.fetch(request)
            if asset is not None:
                return asset
        return None


def create_image_pipeline(client: httpx.AsyncClient) -> ImagePipeline:
    settings = get_settings()
    return ImagePipeline(
        [
            GeneratedImageProvider(
                client=client,
                base_url=settings.image_base_url,
                api_key=settings.image_api_key,
                model=settings.image_model,
                timeout_seconds=settings.image_timeout_seconds,
            ),
            UnsplashImageProvider(
                client=client,
                access_key=settings.unsplash_access_key,
                timeout_seconds=settings.image_timeout_seconds,
            ),
        ]
    )
