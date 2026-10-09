from collections.abc import Awaitable, Callable

import httpx

from app.core.config import get_settings
from app.images.bailian import BailianImageProvider
from app.images.base import ImageAsset, ImageProvider, ImageRequest
from app.images.errors import ImageFetchError
from app.images.generated import GeneratedImageProvider
from app.images.unsplash import UnsplashImageProvider


class ImagePipeline:
    """按配图计划尝试图源；真实对象只用图库，公开错误交给图片状态展示。"""

    def __init__(self, providers: list[ImageProvider]) -> None:
        self._providers = providers

    @property
    def enabled(self) -> bool:
        return any(provider.available() for provider in self._providers)

    async def fetch(self, request: ImageRequest) -> ImageAsset | None:
        providers = self._providers
        if request.require_real or request.preferred_source == "stock":
            providers = sorted(providers, key=lambda p: p.source != "stock")
        if request.preferred_source == "generated":
            providers = sorted(providers, key=lambda p: p.source != "generated")
        failures = []
        for provider in providers:
            if request.require_real and provider.source != "stock":
                continue
            if not provider.available():
                continue
            try:
                asset = await provider.fetch(request)
            except ImageFetchError as error:
                failures.append(str(error))
                continue
            if asset is not None:
                return asset
        if failures:
            raise ImageFetchError("；".join(dict.fromkeys(failures)))
        return None

    def available_for(self, request: ImageRequest) -> bool:
        return any(
            p.available() and (not request.require_real or p.source == "stock")
            for p in self._providers
        )


def create_image_pipeline(
    client: httpx.AsyncClient,
    *,
    reserve: Callable[[str], Awaitable[bool]] | None = None,
) -> ImagePipeline:
    settings = get_settings()
    if settings.image_provider == "bailian":
        primary: ImageProvider = BailianImageProvider(
            client=client,
            api_key=settings.image_api_key,
            model=settings.image_model,
            base_url=settings.image_base_url,
            workspace_id=settings.image_workspace_id,
            timeout_seconds=settings.image_timeout_seconds,
        )
    else:
        primary = GeneratedImageProvider(
            client=client,
            base_url=settings.image_base_url,
            api_key=settings.image_api_key,
            model=settings.image_model,
            timeout_seconds=settings.image_timeout_seconds,
        )

    return ImagePipeline(
        [
            primary,
            UnsplashImageProvider(
                client=client,
                access_key=settings.unsplash_access_key,
                timeout_seconds=settings.image_timeout_seconds,
                reserve=reserve,
            ),
        ]
    )
