"""Preserve topic requirements without injecting unrelated sample material."""

from __future__ import annotations

import re
from collections.abc import Sequence

from app.ingest.models import ParsedDocument, SourceSection

_LEGACY_TOPIC = re.compile(r"^本材料为围绕“(.+?)”自动生成的模拟汇报素材", re.DOTALL)


def build_topic_document(*, topic: str) -> ParsedDocument:
    return ParsedDocument(
        sections=[
            SourceSection(
                level=1,
                heading="主题与要求",
                locator="用户主题输入",
                text=topic.strip(),
            )
        ],
        warnings=["主题内容由 AI 基于通用知识扩展，事实与数据请核实。"],
    )


def topic_request_from_sections(sections: Sequence[dict], *, fallback: str = "") -> str:
    for section in sections:
        text = section.get("text", "").strip()
        if section.get("heading") == "主题与要求" and text:
            return text
        if section.get("heading") == "样稿说明" and (match := _LEGACY_TOPIC.match(text)):
            return match.group(1).strip()
    return "\n\n".join(section.get("text", "").strip() for section in sections).strip() or fallback
