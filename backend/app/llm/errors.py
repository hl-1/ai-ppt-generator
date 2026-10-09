import json

from pydantic import ValidationError


class LLMNotConfiguredError(RuntimeError):
    """未配置可用的 LLM 凭证。上层应提示用户配置，禁止伪造内容。"""


class LLMTimeoutError(TimeoutError):
    """模型请求超过客户端或供应商允许的等待时间。"""


class LLMUnavailableError(RuntimeError):
    """模型服务无法连接、限流或返回服务端错误。"""


class InvalidModelOutputError(ValueError):
    """模型返回内容无法通过契约校验。"""


class InvalidOutlineOutputError(InvalidModelOutputError):
    pass


class InvalidSlideOutputError(InvalidModelOutputError):
    pass


class InvalidSlideEditOutputError(InvalidModelOutputError):
    pass


def safe_error_details(error: Exception) -> dict:
    """Describe failures without logging provider responses or source materials."""
    code = "internal_error"
    for kind, value in (
        (LLMNotConfiguredError, "not_configured"),
        (LLMTimeoutError, "timeout"),
        (LLMUnavailableError, "unavailable"),
        (InvalidModelOutputError, "invalid_output"),
    ):
        if isinstance(error, kind):
            code = value
            break
    details = {"error_code": code, "error_type": type(error).__name__}
    current: BaseException | None = error
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        details["cause_type"] = type(current).__name__
        if isinstance(current, json.JSONDecodeError):
            details.update(json_line=current.lineno, json_column=current.colno)
        if isinstance(current, ValidationError):
            details["validation"] = [
                {"path": list(item["loc"]), "type": item["type"]}
                for item in current.errors(include_input=False, include_url=False)[:5]
            ]
        current = current.__cause__ or current.__context__
    return details
