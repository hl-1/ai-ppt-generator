from __future__ import annotations

import json

from openai import AsyncOpenAI
from pydantic import ValidationError

from app.domain.layout import Layout, Slot, get_layout
from app.domain.slide_draft import SlideDraft
from app.llm.base import SlideGenerationInput
from app.llm.client import JsonChatClient
from app.llm.errors import InvalidSlideOutputError


class DeepSeekSlideGenerator:
    """把一页大纲展开成填进布局槽位的正文内容。

    槽位与容量上限直接写进提示词：布局是硬约束，与其事后裁剪
    模型写超的内容，不如一开始就把可用空间告诉它。
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
        self._chat = JsonChatClient(
            client=client,
            model=model,
            api_key=api_key,
            thinking_enabled=thinking_enabled,
            timeout_seconds=timeout_seconds,
        )

    async def generate(self, payload: SlideGenerationInput) -> SlideDraft:
        layout = get_layout(payload.layout_id)
        content = await self._chat.complete_json(
            system=self._system_prompt(layout),
            user=self._user_prompt(payload, layout),
            purpose="生成页面内容",
        )

        try:
            draft = SlideDraft.model_validate_json(content)
        except ValidationError as error:
            raise InvalidSlideOutputError("模型返回的页面 JSON 不符合约定结构") from error

        self._validate_draft(draft, layout)
        return draft

    def _system_prompt(self, layout: Layout) -> str:
        return (
            "你是 PPT 正文撰写助手。必须只输出一个 JSON 对象，不要 Markdown，不要额外说明。\n"
            'JSON 结构必须为：{"blocks":[...],"speaker_notes":"..."}\n'
            "blocks 中每个元素都必须带 slot_id 与 type，并按类型提供对应字段：\n"
            '- text: {"slot_id":"title","type":"text","text":"..."}\n'
            '- bullets: {"slot_id":"body","type":"bullets","items":["...","..."]}\n'
            '- image: {"slot_id":"visual","type":"image","alt":"这张图应该表达什么"}\n'
            '- kpi: {"slot_id":"kpi_1","type":"kpi","value":"37%","label":"...","note":"..."}\n'
            '- table: {"slot_id":"body","type":"table","header":["..."],"rows":[["..."]]}\n'
            '- chart: {"slot_id":"visual","type":"chart","chart_type":"bar",'
            '"categories":["..."],"series":[{"name":"...","values":[1,2]}],"unit":"%"}\n'
            "硬性约束：\n"
            "1. 只能使用下面列出的 slot_id，每个槽位最多出现一次，必填槽位不得缺失。\n"
            "2. 每个槽位只能使用它声明接受的 type。\n"
            "3. 严格遵守每个槽位的字数与条目上限，宁可少写也不要超出。\n"
            "4. 正文使用中文，写具体结论与事实，不写「本页介绍……」这类空话。\n"
            "5. 数字必须来自给定来源，缺少数据时不要编造，改用文字表述。\n"
            "6. speaker_notes 用 2–3 句话给出讲稿提示。\n"
            f"本页布局为 {layout.id}（{layout.name}）：{layout.usage}"
        )

    def _user_prompt(self, payload: SlideGenerationInput, layout: Layout) -> str:
        body = {
            "deck_title": payload.deck_title,
            "audience": payload.audience,
            "tone": payload.tone,
            "page": {
                "position": payload.position,
                "total_pages": payload.total_pages,
                "title": payload.page_title,
                "objective": payload.objective,
                "key_points": payload.key_points,
            },
            "neighbor_titles": payload.neighbor_titles,
            "slots": [_slot_spec(slot) for slot in layout.slots],
            "sections": [
                {"ref": s.ref, "heading": s.heading, "text": s.text} for s in payload.sections
            ],
        }
        prompt = f"请为以下页面生成正文 JSON。\n{json.dumps(body, ensure_ascii=False)}"
        if payload.issues:
            prompt += (
                "\n上一次生成存在以下问题，请只修正这些问题并保持其余内容稳定：\n"
                + "\n".join(f"- {issue}" for issue in payload.issues)
            )
        return prompt

    def _validate_draft(self, draft: SlideDraft, layout: Layout) -> None:
        # 结构性错误在这里就拦掉，避免把非法槽位写进数据库再靠渲染兜底
        seen: set[str] = set()
        for block in draft.blocks:
            slot = layout.slot_by_id(block.slot_id)
            if slot is None:
                raise InvalidSlideOutputError(f"布局 {layout.id} 不存在槽位 {block.slot_id}")
            if block.slot_id in seen:
                raise InvalidSlideOutputError(f"槽位 {block.slot_id} 被重复填充")
            if block.type not in slot.accepts:
                raise InvalidSlideOutputError(
                    f"槽位 {slot.id} 只接受 {'、'.join(slot.accepts)}，实际为 {block.type}"
                )
            seen.add(block.slot_id)

        missing = [slot.id for slot in layout.slots if slot.required and slot.id not in seen]
        if missing:
            raise InvalidSlideOutputError(f"必填槽位缺少内容：{'、'.join(missing)}")


def _slot_spec(slot: Slot) -> dict:
    capacity = slot.capacity.model_dump(exclude_none=True)
    return {
        "slot_id": slot.id,
        "accepts": list(slot.accepts),
        "required": slot.required,
        "capacity": capacity,
    }
