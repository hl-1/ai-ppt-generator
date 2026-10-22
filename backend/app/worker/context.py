from typing import Any

from app.infrastructure.llm.client import create_chat_model
from app.infrastructure.llm.factory import create_outline_generator, create_slide_generator


async def startup(ctx: dict[str, Any]) -> None:
    # 模型在进程内复用：每个任务新建连接池会显著抬高首字节延迟
    model = create_chat_model()
    ctx["chat_model"] = model
    ctx["outline_generator"] = create_outline_generator(model)
    ctx["slide_generator"] = create_slide_generator(model)


async def shutdown(ctx: dict[str, Any]) -> None:
    model = ctx.get("chat_model")
    client = getattr(model, "async_client", None) if model is not None else None
    if client is not None:
        close = getattr(client, "close", None)
        if close is not None:
            await close()
