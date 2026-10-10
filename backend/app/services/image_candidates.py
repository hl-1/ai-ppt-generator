import hashlib
import json
import uuid

import httpx

from app.core.config import get_settings
from app.core.redis import get_redis
from app.domain.image_planning import search_queries
from app.images.base import ImageCandidate, ImageRequest
from app.images.errors import ImageFetchError
from app.images.unsplash import UnsplashImageProvider
from app.schemas.images import ImageSearchPublic

TTL = 30 * 60


def stock_provider(client: httpx.AsyncClient) -> UnsplashImageProvider:
    settings = get_settings()
    return UnsplashImageProvider(
        client=client,
        access_key=settings.unsplash_access_key,
        timeout_seconds=settings.image_timeout_seconds,
        search_timeout_seconds=settings.stock_search_timeout_seconds,
    )


async def search_candidates(project_id: uuid.UUID, request: ImageRequest) -> ImageSearchPublic:
    signature = hashlib.sha256(request.model_dump_json().encode()).hexdigest()[:32]
    search_id = signature
    key = f"image-candidates:{project_id}:{search_id}"
    cached = await get_redis().get(key)
    if cached:
        return ImageSearchPublic.model_validate_json(cached)
    async with httpx.AsyncClient(trust_env=False) as client:
        candidates = await stock_provider(client).search(request)
    result = ImageSearchPublic(
        search_id=search_id,
        candidates=candidates,
        queries=search_queries(request.query, request.queries),
    )
    await get_redis().set(key, result.model_dump_json(), ex=TTL if candidates else 30)
    return result


async def load_candidate(
    project_id: uuid.UUID, search_id: str, candidate_id: str
) -> ImageCandidate:
    if not search_id.isalnum():
        raise ImageFetchError("候选结果已过期，请重新搜索")
    cached = await get_redis().get(f"image-candidates:{project_id}:{search_id}")
    if not cached:
        raise ImageFetchError("候选结果已过期，请重新搜索")
    result = ImageSearchPublic.model_validate(json.loads(cached))
    candidate = next((item for item in result.candidates if item.id == candidate_id), None)
    if candidate is None:
        raise ImageFetchError("候选图片不存在，请重新搜索")
    return candidate
