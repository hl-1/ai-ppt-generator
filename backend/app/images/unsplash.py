import asyncio
import logging
import re
from collections.abc import Awaitable, Callable
from urllib.parse import urlparse

import httpx

from app.domain.content import ImageSource
from app.domain.image_planning import LANDMARKS, search_queries, subject_terms
from app.images.base import ImageAsset, ImageCandidate, ImageRequest
from app.images.errors import ImageFetchError

logger = logging.getLogger(__name__)
API_BASE = "https://api.unsplash.com"
_PUNCT_RE = re.compile(r"[：:；;，,。.!！？?\u2014\u2013\-_/\\|（）()【】\[\]「」\"'“”‘’…·、]+")
_SPACE_RE = re.compile(r"\s+")
_MAX_QUERY_CHARS = 120
_PEOPLE_RE = re.compile(r"\b(man|woman|person|people|portrait|guard|selfie|wedding)\b", re.I)


class UnsplashImageProvider:
    source: ImageSource = "stock"

    def __init__(
        self,
        *,
        client: httpx.AsyncClient,
        access_key: str,
        timeout_seconds: float = 30,
        reserve: Callable[[str], Awaitable[bool]] | None = None,
    ) -> None:
        self._client = client
        self._access_key = access_key
        self._timeout = timeout_seconds
        self._reserve = reserve

    def available(self) -> bool:
        return bool(self._access_key.strip())

    async def search(self, request: ImageRequest, *, limit: int = 8) -> list[ImageCandidate]:
        if not self.available():
            raise ImageFetchError("图库尚未配置，请上传图片或使用 AI 插图")
        headers = {"Authorization": f"Client-ID {self._access_key}"}
        queries = search_queries(request.query, request.queries)
        queries = list(dict.fromkeys(q for query in queries for q in _search_queries(query)))[:4]
        candidates: dict[str, ImageCandidate] = {}
        terms = subject_terms(request.subject or request.query, request.queries)
        subject = (request.subject or request.query).lower()
        landmark = any(
            name in subject or any(alias.lower() in subject for alias in aliases)
            for name, aliases in LANDMARKS.items()
        )
        needs_match = request.require_real or landmark
        attempts = [(query, _orientation(request.aspect_ratio)) for query in queries]
        if needs_match and queries:
            attempts.append((queries[0], None))
        try:
            async with asyncio.timeout(min(self._timeout, 45)):
                for query, orientation in attempts:
                    params = {"query": query, "per_page": 8, "content_filter": "high"}
                    if orientation:
                        params["orientation"] = orientation
                    response = await self._client.get(
                        f"{API_BASE}/search/photos",
                        headers=headers,
                        params=params,
                        timeout=min(self._timeout, 20),
                    )
                    if response.status_code == 410:
                        continue
                    if response.status_code == 429:
                        raise ImageFetchError("图库请求额度已用完，请稍后重试或上传图片")
                    if response.status_code in {401, 403}:
                        raise ImageFetchError("图库凭证无效或权限不足，请检查配置")
                    response.raise_for_status()
                    for index, photo in enumerate(response.json().get("results") or []):
                        candidate = _candidate(photo, fallback_id=f"legacy-{index}")
                        if candidate and candidate.id not in request.excluded_ids:
                            candidates[candidate.id] = candidate
                    if len(candidates) >= limit and (
                        not needs_match or any(
                            term in item.description.lower()
                            for item in candidates.values() for term in terms
                        )
                    ):
                        break
        except (httpx.TimeoutException, TimeoutError) as error:
            if not candidates:
                raise ImageFetchError("图库检索超时，请重试") from error
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as error:
            raise ImageFetchError("图库暂时不可用，请稍后重试") from error
        for candidate in candidates.values():
            text = candidate.description.lower()
            candidate.metadata_matched = any(term in text for term in terms)
            candidate.match_reason = (
                "描述包含目标对象，尚未进行视觉审图"
                if candidate.metadata_matched
                else "待人工确认主体"
            )

        def rank(candidate: ImageCandidate) -> tuple:
            ratio = candidate.width / candidate.height if candidate.height else request.aspect_ratio
            return (
                not candidate.metadata_matched,
                landmark and bool(_PEOPLE_RE.search(candidate.description)),
                abs(ratio - request.aspect_ratio),
                -candidate.width * candidate.height,
            )

        return sorted(candidates.values(), key=rank)[:limit]

    async def fetch(self, request: ImageRequest) -> ImageAsset | None:
        if not self.available():
            return None
        candidates = await self.search(request)
        last_error = None
        for candidate in candidates:
            if request.require_real and not candidate.metadata_matched:
                continue
            if (
                candidate.width and candidate.height
                and min(candidate.width, candidate.height) < 600
            ):
                continue
            if self._reserve and not await self._reserve(candidate.id):
                continue
            try:
                return await self.download(candidate)
            except ImageFetchError as error:
                last_error = error
        if last_error:
            raise last_error
        return None

    async def download(self, candidate: ImageCandidate) -> ImageAsset:
        if not _allowed_url(candidate.url, "images.unsplash.com"):
            raise ImageFetchError("图库返回的图片地址无效")
        try:
            response = await self._client.get(candidate.url, timeout=self._timeout)
            response.raise_for_status()
            location = candidate.download_location
            if location and _allowed_url(location, "api.unsplash.com"):
                tracked = await self._client.get(
                    location,
                    headers={"Authorization": f"Client-ID {self._access_key}"},
                    timeout=min(self._timeout, 15),
                )
                tracked.raise_for_status()
        except httpx.HTTPError as error:
            raise ImageFetchError("图片下载或图库取用登记失败，请重试") from error
        return ImageAsset(
            data=response.content,
            content_type=response.headers.get("content-type", "image/jpeg"),
            source="stock",
            credit=candidate.credit,
            credit_url=candidate.credit_url,
            asset_id=candidate.id,
        )


def _allowed_url(url: str, host: str) -> bool:
    parsed = urlparse(url)
    return parsed.scheme == "https" and parsed.hostname == host and parsed.port in {None, 443}


def _candidate(photo: dict, *, fallback_id: str) -> ImageCandidate | None:
    urls = photo.get("urls") or {}
    url = urls.get("regular")
    if not url or not _allowed_url(url, "images.unsplash.com"):
        return None
    links = photo.get("links") or {}
    user = photo.get("user") or {}
    description = " ".join(
        str(part)
        for part in (
            photo.get("description"),
            photo.get("alt_description"),
            (photo.get("location") or {}).get("title"),
            " ".join(
                tag.get("title", "") for tag in photo.get("tags", []) if isinstance(tag, dict)
            ),
        )
        if part
    )
    return ImageCandidate(
        id=str(photo.get("id") or fallback_id),
        url=url,
        thumbnail_url=urls.get("small") or url,
        description=description[:800],
        width=photo.get("width") or 0,
        height=photo.get("height") or 0,
        credit=f"Photo by {user.get('name') or 'Unsplash'} on Unsplash",
        credit_url=links.get("html") or "https://unsplash.com",
        author_url=(user.get("links") or {}).get("html") or "https://unsplash.com",
        download_location=links.get("download_location"),
    )


def sanitize_unsplash_query(query: str) -> str:
    cleaned = _SPACE_RE.sub(" ", _PUNCT_RE.sub(" ", query)).strip()
    return cleaned[:_MAX_QUERY_CHARS].rstrip()


def _search_queries(raw: str) -> list[str]:
    primary = sanitize_unsplash_query(raw)
    short = " ".join(primary.split()[:3])[:16].rstrip()
    return list(dict.fromkeys(q for q in (primary, short) if q))


def _orientation(aspect_ratio: float) -> str:
    return (
        "landscape" if aspect_ratio >= 1.2 else "portrait" if aspect_ratio <= 0.85 else "squarish"
    )
