from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel, ValidationError
from pydantic.alias_generators import to_snake
from pydantic.fields import FieldInfo

_LAYOUT_ALIASES = {
    "title": "cover",
    "title_slide": "cover",
    "agenda": "toc",
    "table_of_contents": "toc",
    "chapter": "section",
    "conclusion": "summary",
    "closing": "summary",
    "text": "bullets",
    "text_only": "bullets",
    "bullet": "bullets",
    "bullet_points": "bullets",
    "content": "bullets",
    "two_columns": "two-column",
    "two_col": "two-column",
    "comparison": "two-column",
    "image_text": "image-left",
    "image_and_text": "image-left",
    "line_chart": "chart",
    "bar_chart": "chart",
    "pie_chart": "chart",
    "data_table": "table",
}


def normalize_model_fields(value: Any, fields: Mapping[str, FieldInfo]) -> Any:
    if isinstance(value, BaseModel):
        value = value.model_dump()
    if not isinstance(value, dict):
        return value
    normalized = dict(value)
    for key, item in value.items():
        canonical = to_snake(key)
        if canonical in fields and canonical not in normalized:
            normalized[canonical] = item
    for name, field in fields.items():
        if (
            name in normalized
            and normalized[name] is None
            and not field.is_required()
            and (field.default_factory is not None or field.default is not None)
        ):
            normalized.pop(name)
    return normalized


def normalize_string_list(value: Any) -> Any:
    if isinstance(value, str):
        return [line.strip() for line in value.splitlines() if line.strip()]
    if isinstance(value, list):
        return [item.strip() if isinstance(item, str) else item for item in value]
    return value


def normalize_token(value: str) -> str:
    return to_snake(value.strip()).lower().replace("-", "_").replace(" ", "_")


def normalize_choice(
    value: Any,
    choices: tuple[str, ...],
    *,
    default: str,
    aliases: Mapping[str, str] | None = None,
) -> Any:
    if not isinstance(value, str):
        return value
    token = normalize_token(value)
    token = (aliases or {}).get(token, token)
    return token if token in choices else default


def normalize_layout_id(
    value: str,
    *,
    available: frozenset[str],
    page_role: str,
    evidence_kind: str,
) -> tuple[str, bool]:
    if value in available:
        return value, False
    token = normalize_token(value)
    canonical = _LAYOUT_ALIASES.get(token, token)
    by_token = {normalize_token(layout): layout for layout in sorted(available)}
    matched = by_token.get(token) or by_token.get(normalize_token(canonical))
    if matched is not None:
        return matched, False

    # Layout is presentation metadata: retain the content and choose an installed layout.
    preferred = (
        page_role
        if page_role != "content"
        else {
            "trend": "chart",
            "chart": "chart",
            "kpi": "kpi",
            "table": "table",
            "comparison": "two-column",
        }.get(evidence_kind, "bullets")
    )
    for candidate in (preferred, "bullets", "two-column"):
        if candidate in available:
            return candidate, True
    if not available:
        raise ValueError("No layouts are configured")
    return min(available), True


def model_output_feedback(error: Exception) -> str:
    current: BaseException | None = error
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if isinstance(current, ValidationError):
            # Field paths and error types are enough for repair; omit input materials.
            return "; ".join(
                f"{'.'.join(str(part) for part in item['loc'])}: {item['type']}"
                for item in current.errors(include_input=False, include_url=False)[:5]
            )
        current = current.__cause__
    return str(error)[:600]
