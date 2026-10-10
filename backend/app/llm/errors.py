import json
import re

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


MODEL_ERROR_LABELS = {
    "timeout": "模型请求超时",
    "auth_failed": "模型凭证或访问权限被拒绝",
    "credits_exhausted": "模型额度不足",
    "rate_limited": "模型请求频率受限",
    "request_rejected": "模型名称或请求参数不受支持",
    "not_configured": "模型未配置",
    "invalid_output": "模型输出无法解析",
    "unavailable": "模型服务不可用",
}
NON_RETRYABLE_MODEL_ERRORS = {"auth_failed", "credits_exhausted", "request_rejected", "not_configured"}


def safe_error_details(error: Exception) -> dict:
    """Describe failures without logging provider responses or source materials."""
    code = "internal_error"
    for kind, value in (
        (LLMNotConfiguredError, "not_configured"),
        (LLMTimeoutError, "timeout"),
        (TimeoutError, "timeout"),
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
        response = getattr(current, "response", None)
        status = getattr(current, "status_code", None) or getattr(response, "status_code", None)
        if isinstance(status, int):
            details["http_status"] = status
        body = getattr(current, "body", None)
        if body is None and response is not None:
            try:
                body = response.json()
            except (ValueError, AttributeError):
                pass
        if isinstance(body, dict):
            provider_error = body.get("error") or body.get("Error") or body
            if isinstance(provider_error, dict):
                provider_code = provider_error.get("code") or provider_error.get("Code")
                if provider_code is not None and re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", str(provider_code)):
                    details["provider_code"] = str(provider_code)
        headers = getattr(response, "headers", None)
        if headers:
            try:
                delay = float(headers.get("retry-after", ""))
                if 0 <= delay <= 3600:
                    details["retry_after_seconds"] = delay
            except (ValueError, TypeError):
                pass
        if isinstance(current, json.JSONDecodeError):
            details.update(json_line=current.lineno, json_column=current.colno)
        if isinstance(current, ValidationError):
            details["validation"] = [
                {"path": list(item["loc"]), "type": item["type"]}
                for item in current.errors(include_input=False, include_url=False)[:5]
            ]
        current = current.__cause__ or current.__context__
    provider_code = details.get("provider_code", "").lower()
    if any(
        value in provider_code
        for value in ("freequotaexhausted", "insufficient_quota", "insufficient_balance", "insufficient_credits")
    ) or details.get("http_status") == 402:
        details["error_code"] = "credits_exhausted"
    elif details.get("http_status") in {401, 403}:
        details["error_code"] = "auth_failed"
    elif details.get("http_status") == 429:
        details["error_code"] = "rate_limited"
    elif details.get("http_status") in {400, 404, 422}:
        details["error_code"] = "request_rejected"
    return details
