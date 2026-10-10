import json
from typing import TypeVar
from urllib.parse import urlparse

import httpx
from langchain_core.exceptions import OutputParserException
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.utils.json import parse_json_markdown
from langchain_openai import ChatOpenAI
from openai import APIError, APITimeoutError, LengthFinishReasonError
from pydantic import BaseModel, ValidationError

from app.core.config import Settings, get_settings
from app.llm.errors import (
    MODEL_ERROR_LABELS,
    NON_RETRYABLE_MODEL_ERRORS,
    InvalidModelOutputError,
    LLMNotConfiguredError,
    LLMTimeoutError,
    LLMUnavailableError,
    safe_error_details,
)
from app.llm.normalization import model_output_feedback

T = TypeVar("T", bound=BaseModel)

# LCEL 负责一次结构化调用；有状态的校验/修复放在 LangGraph。
_PROMPT = ChatPromptTemplate.from_messages(
    [
        ("system", "{system}"),
        ("human", "{user}"),
    ]
)


def create_chat_model(settings: Settings | None = None) -> ChatOpenAI:
    """用 ChatOpenAI 对接 DeepSeek 兼容接口，业务层不再持有 OpenAI SDK。"""
    cfg = settings or get_settings()
    kwargs: dict = {
        "model": cfg.llm_model,
        "api_key": cfg.llm_api_key or "not-configured",
        "base_url": cfg.llm_base_url,
        "timeout": cfg.llm_timeout_seconds,
        # 工作流负责显式重试；避免客户端和任务叠加隐式重试。
        "max_retries": 0,
        "extra_body": {
            "thinking": {
                "type": "enabled" if cfg.llm_thinking_enabled else "disabled",
            }
        },
    }
    if (
        not cfg.llm_thinking_enabled
        and cfg.llm_model == "glm-5.3-flashx"
        and urlparse(cfg.llm_base_url).hostname == "tokenhub.tencentmaas.com"
    ):
        # TokenHub FlashX rejects disabled thinking; use the model's supported default.
        kwargs.pop("extra_body")
        kwargs["reasoning_effort"] = "high"
    return ChatOpenAI(**kwargs)


class StructuredChatClient:
    """统一读取模型 JSON，再交给各业务结构规范化和校验。"""

    def __init__(self, *, model: BaseChatModel, api_key: str) -> None:
        self._model = model
        self._api_key = api_key
        self.fatal_error_code: str | None = None
        self._fatal_error: Exception | None = None

    async def complete(
        self,
        schema: type[T],
        *,
        system: str,
        user: str,
        purpose: str,
        max_tokens: int | None = None,
    ) -> T:
        if not self._api_key.strip():
            raise LLMNotConfiguredError(f"未配置 LLM API Key，无法{purpose}")
        if self.fatal_error_code:
            raise LLMUnavailableError(
                MODEL_ERROR_LABELS[self.fatal_error_code]
            ) from self._fatal_error

        model = (
            self._model
            if max_tokens is None
            else self._model.model_copy(update={"max_tokens": max_tokens})
        )
        chain = _PROMPT | model.with_structured_output(schema, method="json_mode", include_raw=True)
        try:
            response = await chain.ainvoke({"system": system, "user": user})
            raw = response.get("raw") if isinstance(response, dict) else None
            if not isinstance(raw, BaseMessage):
                raise InvalidModelOutputError("模型未返回可解析的内容")
            if raw.response_metadata.get("finish_reason") == "length":
                raise InvalidModelOutputError("模型返回内容被截断，请缩短输出后重试")
            content = raw.content
            if isinstance(content, list):
                content = "".join(
                    item if isinstance(item, str) else item.get("text", "")
                    for item in content
                    if isinstance(item, str)
                    or (
                        isinstance(item, dict)
                        and item.get("type") == "text"
                        and isinstance(item.get("text"), str)
                    )
                )
            # Strict JSON decoding prevents a partial-output parser from accepting truncation.
            payload = parse_json_markdown(content, parser=json.loads)
            return schema.model_validate(payload)
        except (TimeoutError, httpx.TimeoutException, APITimeoutError) as error:
            raise LLMTimeoutError("模型请求超时") from error
        except (httpx.HTTPError, APIError) as error:
            code = safe_error_details(error)["error_code"]
            if code in NON_RETRYABLE_MODEL_ERRORS:
                self.fatal_error_code, self._fatal_error = code, error
            raise LLMUnavailableError("模型服务暂不可用") from error
        except LengthFinishReasonError as error:
            raise InvalidModelOutputError("模型返回内容被截断，请缩短输出后重试") from error
        except InvalidModelOutputError:
            raise
        except json.JSONDecodeError as error:
            raise InvalidModelOutputError(
                f"模型返回 JSON 无法解析：{error.msg}，位置 {error.lineno}:{error.colno}"
            ) from error
        except (OutputParserException, ValidationError, ValueError) as error:
            raise InvalidModelOutputError(
                f"模型返回内容不符合约定结构：{model_output_feedback(error)}"
            ) from error
