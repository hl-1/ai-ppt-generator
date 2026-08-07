from typing import Any

import httpx
from openai import AsyncOpenAI

from app.core.config import get_settings
from app.images.pipeline import create_image_pipeline
from app.llm.base import OutlineGenerator, SlideEditGenerator, SlideGenerator
from app.llm.deepseek import DeepSeekOutlineGenerator
from app.llm.relayout import DeepSeekRelayoutGenerator
from app.llm.slide import DeepSeekSlideGenerator
from app.llm.slide_edit import DeepSeekSlideEditGenerator


def create_llm_client() -> AsyncOpenAI:
    settings = get_settings()
    return AsyncOpenAI(
        api_key=settings.llm_api_key or "not-configured",
        base_url=settings.llm_base_url,
        timeout=settings.llm_timeout_seconds,
        max_retries=2,
    )


def create_outline_generator(client: AsyncOpenAI | None = None) -> OutlineGenerator:
    settings = get_settings()
    return DeepSeekOutlineGenerator(
        client=client or create_llm_client(),
        model=settings.llm_model,
        api_key=settings.llm_api_key,
        thinking_enabled=settings.llm_thinking_enabled,
        timeout_seconds=settings.llm_timeout_seconds,
    )


def create_slide_generator(client: AsyncOpenAI | None = None) -> SlideGenerator:
    settings = get_settings()
    return DeepSeekSlideGenerator(
        client=client or create_llm_client(),
        model=settings.llm_model,
        api_key=settings.llm_api_key,
        thinking_enabled=settings.llm_thinking_enabled,
        timeout_seconds=settings.llm_timeout_seconds,
    )


def create_slide_edit_generator(client: AsyncOpenAI | None = None) -> SlideEditGenerator:
    settings = get_settings()
    return DeepSeekSlideEditGenerator(
        client=client or create_llm_client(),
        model=settings.llm_model,
        api_key=settings.llm_api_key,
        thinking_enabled=settings.llm_thinking_enabled,
        timeout_seconds=settings.llm_timeout_seconds,
    )


def create_relayout_generator(client: AsyncOpenAI | None = None) -> DeepSeekRelayoutGenerator:
    settings = get_settings()
    return DeepSeekRelayoutGenerator(
        client=client or create_llm_client(),
        model=settings.llm_model,
        api_key=settings.llm_api_key,
        thinking_enabled=settings.llm_thinking_enabled,
        timeout_seconds=settings.llm_timeout_seconds,
    )


async def startup(ctx: dict[str, Any]) -> None:
    # 客户端在进程内复用：每个任务新建连接池会显著抬高首字节延迟
    client = create_llm_client()
    ctx["llm_client"] = client
    ctx["outline_generator"] = create_outline_generator(client)
    ctx["slide_generator"] = create_slide_generator(client)

    http_client = httpx.AsyncClient()
    ctx["http_client"] = http_client
    ctx["image_pipeline"] = create_image_pipeline(http_client)


async def shutdown(ctx: dict[str, Any]) -> None:
    client = ctx.get("llm_client")
    if client is not None:
        await client.close()

    http_client = ctx.get("http_client")
    if http_client is not None:
        await http_client.aclose()
