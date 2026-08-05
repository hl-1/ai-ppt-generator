from typing import Any

from openai import AsyncOpenAI

from app.llm.errors import InvalidModelOutputError, LLMNotConfiguredError


class JsonChatClient:
    """OpenAI 兼容接口的 JSON 输出封装。

    大纲与页面生成共用同一套调用姿势：强制 JSON 响应格式、显式控制思考
    模式、统一的未配置与空响应处理。生成器只需关心提示词与契约校验。
    """

    def __init__(
        self,
        *,
        client: AsyncOpenAI,
        model: str,
        api_key: str,
        thinking_enabled: bool = False,
        timeout_seconds: float = 60,
    ) -> None:
        self._client = client
        self._model = model
        self._api_key = api_key
        self._thinking_enabled = thinking_enabled
        self._timeout_seconds = timeout_seconds

    async def complete_json(self, *, system: str, user: str, purpose: str) -> str:
        if not self._api_key.strip():
            raise LLMNotConfiguredError(f"未配置 LLM API Key，无法{purpose}")

        create_kwargs: dict[str, Any] = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "response_format": {"type": "json_object"},
            "timeout": self._timeout_seconds,
        }
        # 思考模式默认关闭；关闭时不要传 thinking，避免无谓地拉长延迟
        if self._thinking_enabled:
            create_kwargs["extra_body"] = {"thinking": {"type": "enabled"}}

        response = await self._client.chat.completions.create(**create_kwargs)
        content = response.choices[0].message.content
        if not content:
            raise InvalidModelOutputError("模型返回空内容")
        return content
