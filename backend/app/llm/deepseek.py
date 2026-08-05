from __future__ import annotations

import json

from openai import AsyncOpenAI
from pydantic import ValidationError

from app.domain.layout import load_layouts
from app.domain.outline import OutlineDraft
from app.llm.base import OutlineGenerationInput
from app.llm.client import JsonChatClient
from app.llm.errors import (
    InvalidOutlineOutputError,
    LLMNotConfiguredError,
)

__all__ = [
    "DeepSeekOutlineGenerator",
    "InvalidOutlineOutputError",
    "LLMNotConfiguredError",
]


class DeepSeekOutlineGenerator:
    def __init__(
        self,
        *,
        client: AsyncOpenAI,
        model: str,
        api_key: str,
        thinking_enabled: bool = False,
        timeout_seconds: float = 60,
        layout_ids: frozenset[str] | None = None,
    ) -> None:
        self._chat = JsonChatClient(
            client=client,
            model=model,
            api_key=api_key,
            thinking_enabled=thinking_enabled,
            timeout_seconds=timeout_seconds,
        )
        self._layout_ids = layout_ids if layout_ids is not None else frozenset(load_layouts())

    async def generate(self, payload: OutlineGenerationInput) -> OutlineDraft:
        content = await self._chat.complete_json(
            system=self._system_prompt(),
            user=self._user_prompt(payload),
            purpose="生成大纲",
        )

        try:
            draft = OutlineDraft.model_validate_json(content)
        except ValidationError as error:
            raise InvalidOutlineOutputError("模型返回的大纲 JSON 不符合约定结构") from error

        allowed_refs = {section.ref for section in payload.sections}
        self._validate_draft(draft, page_count=payload.page_count, allowed_refs=allowed_refs)
        return draft

    def _system_prompt(self) -> str:
        layout_list = ", ".join(sorted(self._layout_ids))
        example = {
            "pages": [
                {
                    "title": "封面标题",
                    "objective": "本页要让听众抓住的核心目标",
                    "key_points": ["要点一", "要点二"],
                    "source_refs": ["S1:1"],
                    "layout_id": "cover",
                }
            ]
        }
        return (
            "你是 PPT 大纲规划助手。必须只输出一个 JSON 对象，不要 Markdown，不要额外说明。\n"
            "JSON 结构必须为：\n"
            '{"pages":[{"title":"...","objective":"...","key_points":["..."],'
            '"source_refs":["S1:1"],"layout_id":"cover"}]}\n'
            f"示例：{json.dumps(example, ensure_ascii=False)}\n"
            "硬性约束：\n"
            "1. pages 数组长度必须精确等于用户给定的 page_count。\n"
            "2. 每页 key_points 数量必须在 2–5 个之间。\n"
            "3. source_refs 只能使用用户提供的 ref，不得编造。\n"
            f"4. layout_id 只能从以下合法值中选择：{layout_list}。\n"
            "5. title/objective/key_points 使用中文，信息具体，避免空话。"
        )

    def _user_prompt(self, payload: OutlineGenerationInput) -> str:
        sections_payload = [
            {
                "ref": section.ref,
                "heading": section.heading,
                "level": section.level,
                "text": section.text,
                "locator": section.locator,
            }
            for section in payload.sections
        ]
        body = {
            "title": payload.title,
            "audience": payload.audience,
            "tone": payload.tone,
            "page_count": payload.page_count,
            "sections": sections_payload,
        }
        return (
            f"请根据以下项目参数与来源小节生成大纲 JSON。\n{json.dumps(body, ensure_ascii=False)}"
        )

    def _validate_draft(
        self,
        draft: OutlineDraft,
        *,
        page_count: int,
        allowed_refs: set[str],
    ) -> None:
        if len(draft.pages) != page_count:
            raise InvalidOutlineOutputError(
                f"大纲页数不符：期望 {page_count} 页，实际 {len(draft.pages)} 页"
            )

        for index, page in enumerate(draft.pages, start=1):
            if page.layout_id not in self._layout_ids:
                raise InvalidOutlineOutputError(f"第 {index} 页使用了非法 layout_id")
            for ref in page.source_refs:
                if ref not in allowed_refs:
                    raise InvalidOutlineOutputError(f"第 {index} 页包含未知来源引用")
