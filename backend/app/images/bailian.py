import asyncio
import logging

import httpx

from app.domain.content import ImageSource
from app.images.base import ImageAsset, ImageRequest

logger = logging.getLogger(__name__)

GENERATION_PATH = "/services/aigc/multimodal-generation/generation"

# 百炼 size 格式为「宽*高」；按槽位宽高比就近选，减少后续裁切损失
SIZES: tuple[tuple[float, str], ...] = (
    (1.0, "1328*1328"),
    (1.5, "1664*928"),
    (0.667, "928*1664"),
)


class BailianImageProvider:
    """阿里云百炼 DashScope multimodal-generation 文生图适配器。

    qwen-image-3.0 等模型不支持 OpenAI compatible-mode，必须走原生接口。
    """

    source: ImageSource = "generated"

    def __init__(
        self,
        *,
        client: httpx.AsyncClient,
        api_key: str,
        model: str,
        base_url: str = "https://dashscope.aliyuncs.com/api/v1",
        workspace_id: str = "",
        timeout_seconds: float = 60,
    ) -> None:
        self._client = client
        self._api_key = api_key
        self._model = model
        self._timeout = timeout_seconds
        self._base_url = _resolve_base_url(base_url, workspace_id)

    def available(self) -> bool:
        return bool(self._api_key.strip())

    async def fetch(self, request: ImageRequest) -> ImageAsset | None:
        if not self.available():
            return None

        try:
            if self._model.startswith(("wanx", "wan2.")):
                return await self._fetch_async(request)
            response = await self._client.post(
                f"{self._base_url}{GENERATION_PATH}",
                headers={"Authorization": f"Bearer {self._api_key}"},
                json={
                    "model": self._model,
                    "input": {
                        "messages": [
                            {
                                "role": "user",
                                "content": [{"text": request.prompt}],
                            }
                        ]
                    },
                    "parameters": {
                        "size": _closest_size(request.aspect_ratio),
                        "n": 1,
                        "watermark": False,
                        "prompt_extend": True,
                    },
                },
                timeout=self._timeout,
            )
            response.raise_for_status()
            payload = response.json()
            if payload.get("code"):
                logger.warning(
                    "百炼生图业务失败，降级到下一级图源：%s %s",
                    payload.get("code"),
                    payload.get("message"),
                )
                return None
            url = _extract_image_url(payload)
            if not url:
                return None
            image = await self._client.get(url, timeout=self._timeout)
            image.raise_for_status()
        except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError) as error:
            logger.warning("百炼生图失败，降级到下一级图源：%s", error)
            return None

        return ImageAsset(data=image.content, content_type="image/png", source="generated")

    async def _fetch_async(self, request: ImageRequest) -> ImageAsset | None:
        headers = {"Authorization": f"Bearer {self._api_key}"}
        sizes = ((1.0, "1024*1024"), (1.777, "1280*720"), (0.5625, "720*1280"))
        size = min(sizes, key=lambda pair: abs(pair[0] - request.aspect_ratio))[1]
        try:
            async with asyncio.timeout(self._timeout):
                response = await self._client.post(
                    f"{self._base_url}/services/aigc/text2image/image-synthesis",
                    headers={**headers, "X-DashScope-Async": "enable"},
                    json={
                        "model": self._model,
                        "input": {"prompt": request.prompt},
                        "parameters": {"size": size, "n": 1},
                    },
                    timeout=self._timeout,
                )
                response.raise_for_status()
                payload = response.json()
                if payload.get("code"):
                    logger.warning("image submission rejected code=%s", payload.get("code"))
                    return None
                task_id = payload.get("output", {}).get("task_id")
                if not task_id:
                    return None
                # Submit once; only status reads are retried to avoid duplicate paid tasks.
                while True:
                    response = await self._client.get(
                        f"{self._base_url}/tasks/{task_id}",
                        headers=headers,
                        timeout=min(self._timeout, 20),
                    )
                    if response.status_code == 429 or response.status_code >= 500:
                        await asyncio.sleep(2)
                        continue
                    response.raise_for_status()
                    payload = response.json()
                    output = payload.get("output", {})
                    state = output.get("task_status")
                    if state == "SUCCEEDED":
                        results = output.get("results") or []
                        url = results[0].get("url") if results else None
                        if not url:
                            return None
                        image = await self._client.get(url, timeout=self._timeout)
                        image.raise_for_status()
                        return ImageAsset(
                            data=image.content, content_type="image/png", source="generated"
                        )
                    if state not in {"PENDING", "RUNNING"} or payload.get("code"):
                        logger.warning(
                            "image task failed state=%s code=%s",
                            state,
                            output.get("code") or payload.get("code"),
                        )
                        return None
                    await asyncio.sleep(2)
        except TimeoutError:
            logger.warning("image task exceeded time budget")
            return None


def _resolve_base_url(base_url: str, workspace_id: str) -> str:
    workspace = workspace_id.strip()
    if workspace:
        return f"https://{workspace}.cn-beijing.maas.aliyuncs.com/api/v1"
    return base_url.rstrip("/")


def _closest_size(aspect_ratio: float) -> str:
    return min(SIZES, key=lambda item: abs(item[0] - aspect_ratio))[1]


def _extract_image_url(payload: dict) -> str | None:
    choices = payload.get("output", {}).get("choices") or []
    if not choices:
        return None
    content = choices[0].get("message", {}).get("content") or []
    for item in content:
        if isinstance(item, dict) and item.get("image"):
            return str(item["image"])
    return None
